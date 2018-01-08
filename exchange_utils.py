from math import floor
from time import sleep

from auth import *


# Exception decorator to retry functions upon ccxt exceptions
def retry_on_exception(timeout, retries=10):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for _ in range(retries):
                try:
                    return func(*args, **kwargs)
                except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                    print(e)
                    sleep(timeout)
                    continue
            print(f'{func.__name__} failed to execute after {retries} retries.')
            return None
        return wrapper
    return decorator


# Returns the balance of the ticker in the account.
@retry_on_exception(2)
def fetch_balance(ticker, account='free'):
    return float(exchange.fetch_balance()[ticker][account])


# Returns a list of tickers with non-zero balances (at least 1) in the account.
# Does not list ETH, BTC, BNB, or USDT.
@retry_on_exception(2)
def fetch_nonzero_balances():
    balances = exchange.fetch_balance()['total']
    balances.pop('ETH', None)
    balances.pop('BTC', None)
    balances.pop('USDT', None)
    balances.pop('BNB', None)
    return [ticker for ticker in balances.keys() if balances[ticker] >= 1]


# Returns data for the ticker.
@retry_on_exception(2)
def fetch_ticker(ticker, pair='ETH'):
    data = exchange.fetch_ticker(ticker + f'/{pair}')
    return {'bid': float(data['bid']),           'change': float(data['change']),
            'high': float(data['high']),         'low': float(data['low']),
            'volume': float(data['baseVolume']), 'last': float(data['last'])}


# Returns a dictionary w/ the prices and percent changes of all cryptos passed in.
def fetch_tickers(tickers, pair='ETH'):
    return {ticker: fetch_ticker(ticker, pair) for ticker in tickers}


# Places a market sell order for the ticker using the
# given percentage of the available balance.
@retry_on_exception(2)
def sell(ticker, percent, pair='ETH'):
    order = exchange.create_market_sell_order(
                ticker + f'/{pair}',
                floor(fetch_balance(ticker) * (percent/100)))
    return order


# Places a limit sell order for the ticker using the
# given percentage of the available balance.
@retry_on_exception(2)
def limit_sell(ticker, percent, price, pair='ETH'):
    order = exchange.create_limit_sell_order(
        ticker + f'/{pair}',
        floor(fetch_balance(ticker) * (percent/100)),
        price)
    return order


# Places a market sell order for each of the tickers at the given percentage of
# the total balance.
def sell_tickers(tickers, percent, pair='ETH'):
    return [sell(ticker, percent, pair) for ticker in tickers]


# Places a market buy order for the ticker using the specified percentage of the pair
# currency. If the order does not go through, and auto_adjust is True,
#  another is placed for 1% less volume.
def buy(ticker, pair_percent, pair='ETH', auto_adjust=True):
    amount = floor(fetch_balance(pair) * (pair_percent/100) / fetch_ticker(ticker)['last'])
    buy_placed = False
    while not buy_placed:
        try:
            order = exchange.create_market_buy_order(ticker + f'/{pair}', amount)
        except ccxt.InsufficientFunds as e:
            if auto_adjust:
                amount *= 0.99 # step down by 1% until order placed
            sleep(1)
            continue
        except (ccxt.ExchangeError, ccxt.NetworkError) as e:
            if auto_adjust and e.__class__.__name__ == 'ExchangeError':
                amount *= 0.99 # step down by 1% until order placed
            print(e)
            sleep(1)
            continue
        buy_placed = True
    return order


# Places a limit buy order for the ticker. If the order does
# not go through, and auto_adjust is True, another is placed for 1% less volume.
def limit_buy(ticker, pair_percent, price, pair='ETH', auto_adjust=True):
    amount = floor(fetch_balance(pair) * (pair_percent/100) / price)
    buy_placed = False
    while not buy_placed:
        try:
            order = exchange.create_limit_buy_order(
                ticker + f'/{pair}',
                amount,
                price)
        except (ccxt.ExchangeError, ccxt.NetworkError) as e:
            if auto_adjust and e.__class__.__name__ == 'ExchangeError':
                amount *= 0.99 # step down by 1% until order placed
            print(e)
            sleep(1)
            continue
        buy_placed = True
    return order


# Places a market buy order for each of the cryptos in the data with
# an equal amount of ether.
def buy_tickers(tickers, pair='ETH'):
    pair_percentage = 100 / len(tickers)
    return [buy(ticker, pair_percentage, pair) for ticker in tickers]


# Swaps a given percentage of one currency into another at market.
def swap(this, that, percent, pair='ETH'):
    sell = sell(this, percent, pair)
    pair_amount = sell['info']['origQty'] * sell['info']['price']
    pair_percent = pair_amount / fetch_balance(pair) * 100
    buy = buy(that, pair_percent, pair)
    return (sell, buy)


# Swaps a given percentage of this for that. Sells this at the given percentage increase
# and buys that at the given percentage decrease.
def swap_limit(this, that, percentage, this_increase, that_decrease, pair='ETH'):
    sell = limit_sell(this, percentage, fetch_ticker(this)['bid'] * (that_increase/100), pair)
    pair_amount = sell['info']['origQty'] * sell['info']['price']
    buy_price = fetch_ticker(that)['bid'] * (100-that_decrease/100)
    pair_percent = pair_amount / fetch_balance(pair) * 100
    buy = limit_buy(that, pair_percent, buy_price, pair)
    return (sell, buy)


# Cancels an order given the order id, ticker, and pair.
@retry_on_exception(2)
def cancel_order(order_id, ticker, pair='ETH'):
    exchange.cancel_order(order_id, ticker + f'/{pair}')


# Cancels all open orders for the given ticker.
def cancel_open_orders(ticker, pair='ETH'):
    for order in exchange.fetch_open_orders(ticker + f'/{pair}'):
        cancel_order(order['info']['orderId'], ticker, pair)


# Cancels all open orders for the given tickers (For pairs ETH and BTC).
# By default attempts to cancel all nonzero balance coins.
# Pass in multiple tickers separated by commas, example:
#   cancel_all_orders('TRX', 'ADA', 'ICX')
def cancel_all_orders(*tickers):
    tickers = tickers if len(tickers) > 0 else fetch_nonzero_balances()
    for ticker in tickers:
        cancel_open_orders(ticker, 'ETH')
        cancel_open_orders(ticker, 'BTC')


# Returns the usd balance of the ticker.
def get_usd_balance(ticker, pair='ETH'):
    pair_usd = fetch_ticker(pair, 'USDT')['last']
    return pair_usd * fetch_balance(ticker, 'total') * fetch_ticker(ticker, pair)['last']


# Returns the usd balance for a given pair (BTC|ETH|USDT|BNB)
def get_pair_usd_balance(pair):
    return fetch_balance(pair, 'total') * fetch_ticker(pair, 'USDT')['last']

def get_pair_bnb_balance(pair):
    return fetch_balance(pair, 'total') * fetch_ticker(pair, 'BNB')['last']

# Returns the equivalent USD amount of all cryptos in the account.
def get_portfolio():
    pair_total = get_pair_usd_balance('ETH') + get_pair_usd_balance('BTC') + get_pair_usd_balance('BNB') + fetch_balance('USDT')
    balances = fetch_nonzero_balances()
    return round(pair_total + sum(get_usd_balance(ticker) for ticker in balances), 2)


# Places a market sell order for the full amount of each of the cryptos in WATCHING.
# Used to redistrubute total funds into all cryptos when distribution becomes too skewed.
def normalize_balances(pair='ETH'):
    tickers = fetch_nonzero_balances()
    sells = sell_tickers(tickers, 100, pair)
    buys = buy_tickers(tickers, pair)
    return (sells, buys)

def find_dust()
    coins = exchange.fetch_balance()['total']
    coins.pop('ETH', None)
    coins.pop('BTC', None)
    coins.pop('USDT', None)
    coins.pop('BNB', None)
    return [ticker for ticker in coins.keys() if coins[ticker] < 1]

def clean_dust()
    dustcoins = find_dust()
    for coin in dustcoins:
        if get_pair_bnb_balance(coin) > 1:
            sell(coin, 100, 'BNB')
        else:
            while get_pair_bnb_balance(coin) < 1:
                try:
                    exchange.create_market_buy_order(ticker + '/ETH', 1)
                except ccxt.InsufficientFunds as e:
                    print(e)
                    return
                except (ccxt.ExchangeError, ccxt.NetworkError) as e:
                    print(e)
                    return
            sell(coin, 100, 'BNB')