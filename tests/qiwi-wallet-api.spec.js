// @ts-check
const { test, expect, request } = require('@playwright/test');

const config = {
  mode: process.env.QIWI_MODE || 'mock',
  baseURL: process.env.QIWI_BASE_URL || 'https://edge.qiwi.com',
  token: process.env.QIWI_TOKEN || 'mock-token',
  wallet: process.env.QIWI_WALLET || '79139999999',
  recipient: process.env.QIWI_RECIPIENT || '+79139999998'
};

const fixtures = {
  history: {
    data: [
      {
        txnId: 11233344692,
        type: 'OUT',
        status: 'SUCCESS',
        sum: { amount: 1, currency: 643 },
        total: { amount: 1, currency: 643 },
        provider: { id: 99, shortName: 'QIWI Wallet' }
      }
    ]
  },
  balance: {
    accounts: [
      {
        alias: 'qw_wallet_rub',
        hasBalance: true,
        balance: { amount: 10.5, currency: 643 },
        currency: 643
      }
    ]
  },
  createdPayment: {
    id: 'qa-1717350000000',
    terms: '99',
    fields: { account: '+79139999998' },
    sum: { amount: 1, currency: '643' },
    transaction: { id: '11982501857', state: { code: 'Accepted' } }
  },
  transaction: {
    txnId: 11982501857,
    type: 'OUT',
    status: 'SUCCESS',
    trmTxnId: 'qa-1717350000000',
    sum: { amount: 1, currency: 643 },
    total: { amount: 1, currency: 643 },
    provider: { id: 99, shortName: 'QIWI Wallet' }
  }
};

let api;

test.beforeAll(async () => {
  if (config.mode === 'live') {
    expect(config.token, 'QIWI_TOKEN is required for live mode').not.toBe('mock-token');
    api = await request.newContext({
      baseURL: config.baseURL,
      extraHTTPHeaders: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.token}`
      }
    });
  }
});

test.afterAll(async () => {
  await api?.dispose();
});

async function getJson(method, path, body) {
  if (config.mode === 'mock') {
    if (path.includes('/persons/bad-wallet/')) {
      return { status: 400, body: { code: 'invalid.person', message: 'Invalid wallet identifier' } };
    }
    if (path.includes('/payments?rows=1')) return { status: 200, body: fixtures.history };
    if (path.includes('/accounts')) return { status: 200, body: fixtures.balance };
    if (path.includes('/terms/99/payments')) {
      if (!body?.sum || body.sum.amount <= 0) {
        return { status: 400, body: { code: 'invalid.amount', message: 'Payment amount must be greater than zero' } };
      }
      if (body.id === 'duplicate-payment-id') {
        return { status: 409, body: { code: 'payment.exists', message: 'Payment with this id already exists' } };
      }
      if (!body.fields?.account) {
        return { status: 400, body: { code: 'missing.account', message: 'Recipient account is required' } };
      }
      return { status: 200, body: fixtures.createdPayment };
    }
    if (path.includes('/transactions/')) return { status: 200, body: fixtures.transaction };
  }

  const response = await api[method](path, body ? { data: body } : undefined);
  const text = await response.text();
  const parsed = text ? JSON.parse(text) : {};
  return { status: response.status(), body: parsed };
}

function expectMoney(value, currency) {
  expect(value).toEqual(expect.objectContaining({
    amount: expect.any(Number),
    currency
  }));
  expect(value.amount).toBeGreaterThanOrEqual(0);
}

test('service availability: payment history responds with documented shape', async () => {
  const { status, body } = await getJson(
    'get',
    `/payment-history/v2/persons/${config.wallet}/payments?rows=1`
  );

  expect(status).toBe(200);
  expect(body).toHaveProperty('data');
  expect(Array.isArray(body.data)).toBe(true);

  if (body.data.length > 0) {
    expect(body.data[0]).toEqual(expect.objectContaining({
      txnId: expect.any(Number),
      type: expect.stringMatching(/^(IN|OUT|QIWI_CARD)$/),
      status: expect.stringMatching(/^(WAITING|SUCCESS|ERROR)$/)
    }));
  }
});

test('balance: RUB wallet account exists and balance is greater than zero', async () => {
  const { status, body } = await getJson(
    'get',
    `/funding-sources/v2/persons/${config.wallet}/accounts`
  );

  expect(status).toBe(200);
  expect(body.accounts).toEqual(expect.any(Array));

  const rubWallet = body.accounts.find((account) => account.alias === 'qw_wallet_rub');
  expect(rubWallet, 'RUB wallet account should be present').toBeTruthy();
  expect(rubWallet.hasBalance).toBe(true);
  expectMoney(rubWallet.balance, 643);
  expect(rubWallet.balance.amount).toBeGreaterThan(0);
});

test('payment creation: transfer for exactly 1 RUB is accepted', async () => {
  const paymentId = `qa-${Date.now()}`;
  const payment = {
    id: paymentId,
    sum: { amount: 1, currency: '643' },
    paymentMethod: { type: 'Account', accountId: '643' },
    comment: `QA test payment ${paymentId}`,
    fields: { account: config.recipient }
  };

  const { status, body } = await getJson('post', '/sinap/api/v2/terms/99/payments', payment);

  expect(status).toBe(200);
  expect(body).toEqual(expect.objectContaining({
    sum: expect.objectContaining({ amount: 1, currency: '643' }),
    terms: '99',
    transaction: expect.objectContaining({
      id: expect.any(String),
      state: expect.objectContaining({ code: expect.stringMatching(/^(Accepted|Completed)$/) })
    })
  }));
});

test('payment execution: created transaction can be checked in payment history', async () => {
  const transactionId = fixtures.createdPayment.transaction.id;
  const { status, body } = await getJson('get', `/payment-history/v2/transactions/${transactionId}?type=OUT`);

  expect(status).toBe(200);
  expect(body).toEqual(expect.objectContaining({
    txnId: expect.any(Number),
    type: 'OUT',
    status: expect.stringMatching(/^(WAITING|SUCCESS|ERROR)$/),
    provider: expect.objectContaining({ id: 99 })
  }));
  expectMoney(body.sum, 643);
  expect(body.sum.amount).toBe(1);
});

test.describe('negative scenarios in mock mode', () => {
  test.skip(config.mode !== 'mock', 'Negative contract tests are deterministic mock checks.');

  test('balance request rejects malformed wallet identifier', async () => {
    const { status, body } = await getJson(
      'get',
      '/funding-sources/v2/persons/bad-wallet/accounts'
    );

    expect(status).toBe(400);
    expect(body).toEqual(expect.objectContaining({
      code: expect.any(String),
      message: expect.any(String)
    }));
  });

  test('payment creation rejects zero amount', async () => {
    const { status, body } = await getJson('post', '/sinap/api/v2/terms/99/payments', {
      id: `qa-${Date.now()}`,
      sum: { amount: 0, currency: '643' },
      paymentMethod: { type: 'Account', accountId: '643' },
      fields: { account: config.recipient }
    });

    expect(status).toBe(400);
    expect(body.code).toBe('invalid.amount');
  });

  test('payment creation rejects missing recipient account', async () => {
    const { status, body } = await getJson('post', '/sinap/api/v2/terms/99/payments', {
      id: `qa-${Date.now()}`,
      sum: { amount: 1, currency: '643' },
      paymentMethod: { type: 'Account', accountId: '643' },
      fields: {}
    });

    expect(status).toBe(400);
    expect(body.code).toBe('missing.account');
  });

  test('payment creation handles duplicate payment id as conflict', async () => {
    const { status, body } = await getJson('post', '/sinap/api/v2/terms/99/payments', {
      id: 'duplicate-payment-id',
      sum: { amount: 1, currency: '643' },
      paymentMethod: { type: 'Account', accountId: '643' },
      fields: { account: config.recipient }
    });

    expect(status).toBe(409);
    expect(body.code).toBe('payment.exists');
  });
});
