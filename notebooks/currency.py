"""Convert IBM AML HI-Small amounts to US Dollars.

The dataset has no exchange-rate column. Each converted payment (payment
currency != receiving currency) implies a rate: amount_received / amount_paid.
IBM's generator uses ONE fixed rate per currency, so the table below is the
median of those implied rates over all converted payments into USD
(checked 17 Oct on all 5,078,345 rows: Euro/Pound/Riyal/Rupee/Bitcoin vary
< 0.3%; the reverse direction USD->currency agrees within 0.06%).

Usage (notebook 02, before the features are built):
    from currency import to_usd
    amt_paid = to_usd(df['amount_paid'], df['payment_currency'])
    amt_recv = to_usd(df['amount_received'], df['receiving_currency'])
"""
import numpy as np
import pandas as pd

# US Dollars per 1 unit of each currency
USD_PER_UNIT = {
    'US Dollar':         1.0,
    'Bitcoin':           11881.623158,
    'UK Pound':          1.291656,
    'Euro':              1.171783,
    'Swiss Franc':       1.092896,
    'Canadian Dollar':   0.757978,
    'Australian Dollar': 0.707814,
    'Shekel':            0.296121,
    'Saudi Riyal':       0.266588,
    'Brazil Real':       0.177101,
    'Yuan':              0.149307,
    'Mexican Peso':      0.047297,
    'Rupee':             0.013616,
    'Ruble':             0.012853,
    'Yen':               0.009488,
}


def to_usd(amount, currency):
    """Return amounts in USD as a float64 numpy array.

    Fails loudly if a currency is not in the table, rather than producing NaNs.
    """
    rate = pd.Series(currency).astype(str).map(USD_PER_UNIT)
    missing = sorted(pd.Series(currency).astype(str)[rate.isna()].unique())
    if missing:
        raise KeyError(f'No USD rate for: {missing}')
    return np.asarray(amount, dtype='float64') * rate.to_numpy(dtype='float64')


def check_rates(df, tolerance=0.01):
    """Re-derive the rates from the data and compare with the table.

    Expects columns amount_paid, payment_currency, amount_received,
    receiving_currency (names from notebook 01). Returns the comparison table;
    raises if any currency differs from the table by more than `tolerance`.
    """
    pc = df['payment_currency'].astype(str)
    rc = df['receiving_currency'].astype(str)
    x = df[(rc == 'US Dollar') & (pc != 'US Dollar')]
    implied = (x['amount_received'] / x['amount_paid']).groupby(pc[x.index]).median()
    table = pd.DataFrame({'implied': implied,
                          'table': pd.Series(USD_PER_UNIT).reindex(implied.index)})
    table['rel_diff'] = (table['implied'] / table['table'] - 1).abs()
    bad = table[table['rel_diff'] > tolerance]
    if len(bad):
        raise AssertionError(f'Rates differ from table:\n{bad}')
    return table
