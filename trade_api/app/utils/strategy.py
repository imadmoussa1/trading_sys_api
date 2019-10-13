import sys
import fxcmpy
import time
import numpy as np
import pandas as pd

import datetime as dt
from pytz import timezone
from pyti.relative_strength_index import relative_strength_index as rsi
### COLOR
RED   = "\033[0;31m"
BLUE  = "\033[0;34m"
GREEN = "\033[0;32m"
RESET = "\033[0;0m"
### Time zone
est = timezone('US/Eastern')

### timeframe ###
# minutes: m1, m5, m15 and m30,
# hours: H1, H2, H3, H4, H6 and H8,
# one day: D1,
# one week: W1,
# one month: M1
#############################

###### USER PARAMETERS ######

symbol = 'EUR/USD'
timeframe = "m1"        # (m1,m5,m15,m30,H1,H2,H3,H4,H6,H8,D1,W1,M1)
starttime = "17:20:00"
endtime = "16:50:00"
rsi_periods = 14
upper_rsi = 70.0
lower_rsi = 30.0
amount = 1

max_open_order = 20

# stop to minmize the loss, adn we can replace by diff postions
max_gain_point = 30
stop = -max_gain_point*2
# limit max can we reach of gain, in case we have a problem in the system.
limit = max_gain_point*4
limit_index = max_gain_point/10000
temp_bid = 0
#############################

# Global Variables
pricedata = None
numberofcandles = 300
first_position = True
first_position_price = 0
block_spread_init = limit_index/max_open_order
block_spread_cum = 0

# Connect to FXCM API
con = fxcmpy.fxcmpy(config_file='/run/secrets/fxcm', server='demo')
# con = fxcmpy.fxcmpy(config_file='fxcm_real.cfg', server='real')
con.is_connected()
# Connection your FXCM id account are retrieved.
con.get_account_ids()
# subscribe to stream
con.subscribe_market_data(symbol)
# Return instruments of FXCM
def instruments():
  instruments = con.get_instruments()
  print(instruments)
  return instruments

# This function runs once at the beginning of the strategy to run initial one-time processes/computations
def Prepare():
  global pricedata

  print("Requesting Initial Price Data...")
  pricedata = con.get_candles(symbol, period=timeframe, number=numberofcandles)
  # print(pricedata)
  print("Initial Price Data Received...")

# Get latest close bar prices and run Update() function every close of bar/candle
def StrategyHeartBeat():
  while True:
    try:
      currenttime = dt.datetime.now(est)
      if timeframe == "m1" and GetLatestPriceData():
        Update()
      elif timeframe == "m5" and currenttime.second == 0 and currenttime.minute % 5 == 0 and GetLatestPriceData():
        Update()
        time.sleep(240)
      elif timeframe == "m15" and currenttime.second == 0 and currenttime.minute % 15 == 0 and GetLatestPriceData():
        Update()
        time.sleep(840)
      elif timeframe == "m30" and currenttime.second == 0 and currenttime.minute % 30 == 0 and GetLatestPriceData():
        Update()
        time.sleep(1740)
      elif currenttime.second == 0 and currenttime.minute == 0 and GetLatestPriceData():
        Update()
        time.sleep(3540)
      time.sleep(1)
    except Exception as e:
      print(e)

# Returns True when pricedata is properly updated
def GetLatestPriceData():
  global pricedata

  # Normal operation will update pricedata on first attempt
  new_pricedata = con.get_candles(symbol, period=timeframe, number=numberofcandles)
  if new_pricedata.index.values[len(new_pricedata.index.values)-1] != pricedata.index.values[len(pricedata.index.values)-1]:
    pricedata= new_pricedata
    return True

  counter = 0
  # If data is not available on first attempt, try up to 3 times to update pricedata
  while new_pricedata.index.values[len(new_pricedata.index.values)-1] == pricedata.index.values[len(pricedata.index.values)-1] and counter < 3:
    print("No updated prices found, trying again in 10 seconds...")
    counter+=1
    time.sleep(10)
    new_pricedata = con.get_candles(symbol, period=timeframe, number=numberofcandles)
  if new_pricedata.index.values[len(new_pricedata.index.values)-1] != pricedata.index.values[len(pricedata.index.values)-1]:
    pricedata = new_pricedata
    return True
  else:
    return False

def Update():
  log_dic = {}
  global first_position, temp_bid, first_position_price, block_spread_cum
  pd.set_option('display.max_columns', None)
  print(str(dt.datetime.now(est)) + "  " + timeframe + " Bar Closed - Running Update Function...")
  log_dic['timeframe'] = dt.datetime.now(est)
  print_color("ACCOUNT", 0)
  print(con.get_accounts().loc[:, ['balance', 'equity', 'usableMargin','usableMarginPerc', 'dayPL', 'grossPL', 'usdMr']])
  log_dic['accounts'] = {
    'balance': con.get_accounts()['balance'],
    'equity': con.get_accounts()['equity'],
    'usableMargin': con.get_accounts()['usableMargin'],
    'usableMarginPerc': con.get_accounts()['usableMarginPerc'],
    'dayPL': con.get_accounts()['dayPL'],
    'grossPL': con.get_accounts()['grossPL'],
    'usdMr': con.get_accounts()['usdMr']
  }
  print_color("SUMMARY", 0)
  print(con.get_summary())

  openpositions = con.get_open_positions()
  last_price = con.get_last_price(symbol)
  last_bid = last_price["Bid"]
  last_ask = last_price["Ask"]

  print_color("LAST PRICE", last_bid-temp_bid)
  print("Close Price: " + str(pricedata['bidclose'][len(pricedata)-1]))

  print(last_price)
  log_dic['price'] = {
    'bid': last_price["Bid"],
    'ask': last_price["Ask"],
    'high': last_price["High"],
    'low': last_price["Low"],
  }
  # BID price to close BUY order
  # ASK price to close SELL order

  # Entry Logic
  if isTradingTime():
    print_color("TradingTime", None)
    if first_position:
      print("First position")
      print("BUY SIGNAL!")
      print("Opening Buy Trade...")

      first_position_price = last_bid if first_position_price==0 else first_position_price
      log_dic['block_center_price'] = first_position_price
      log_dic['block_spread'] = block_spread_init
      log_dic['buy_trade_count'] = countOpenTrades("B")
      log_dic['sell_trade_count'] = countOpenTrades("S")
      log_dic['max_open_trade'] = max_open_order

      print(first_position_price,
       block_spread_cum,
        first_position_price - last_bid ,
         abs(first_position_price - last_bid) >= block_spread_cum)

      if abs(first_position_price - last_bid) >= block_spread_cum:
        block_spread_cum += block_spread_init
        enter("B")
        enter("S")
      if (countOpenTrades("B")+countOpenTrades("S") ) >= max_open_order:
        first_position = False
    else:
      print("First position was opened")

    # Exit Logic
    # we have Buy Trade(s), Close Buy Trade(s)
    total_pl = openpositions['visiblePL'].sum()
    total_gross_pl = openpositions['grossPL'].sum()
    print_color("PL", total_gross_pl)
    print("Visible PL Total: %f ----- Gross PL Total: %f" %(total_pl,total_gross_pl))
    log_dic['total_gross_pl'] = total_gross_pl
    log_dic['total_visible_pl'] = total_pl
    print_color("Sell Positions", -1)
    if countOpenTrades("S") > 0:
      # check the Sell open postions
      sell_postions = openpositions.loc[openpositions['isBuy'] == False].copy()
      # Calcualte the limit index of sell positions ( open price - current price )
      sell_postions.loc[:,'limit_index'] = sell_postions.open - last_ask
      log_dic['sell_postions'] = sell_postions
      print_postion(sell_postions)
      # Close the sell position with limit index higher than our predifined limit index
      sell_position_to_close = sell_postions.loc[(sell_postions['limit_index'] > limit_index) & (sell_postions['visiblePL'] > 0)].copy()
      # Check if we have position ready to be closed
      if not sell_position_to_close.empty:
        print_color("Sell Positions to close", 1)
        print_postion(sell_position_to_close)
        # Close all positions
        for index, position in sell_position_to_close.iterrows():
          exit(position)
          # Open new Sell positon to replace the closed one on the sell price
          if (countOpenTrades("S") < max_open_order-1):
            print_color("open 1 SELL postions", 0)
            enter("S")

    print_color("Buy Positions", 1)
    if countOpenTrades("B") > 0:
      buy_postions = openpositions.loc[openpositions['isBuy'] == True].copy()
      buy_postions.loc[:,'limit_index'] = last_bid - buy_postions.open
      log_dic['buy_postions'] = buy_postions
      print_postion(buy_postions)
      buy_position_to_close = buy_postions.loc[(buy_postions['limit_index'] >= limit_index) & (buy_postions['visiblePL'] > 0)].copy()
      if not buy_position_to_close.empty:
        print_color("Buy Positions to close", 1)
        print_postion(buy_position_to_close)
        for index, position in buy_position_to_close.iterrows():
          exit(position)
          if (countOpenTrades("B") < max_open_order-1):
            print_color("open 1 BUY postions", 0)
            enter("B")

    print_color("Update Function Completed", None)
    temp_bid = last_bid
    # we have Sell Trade(s), Close Sell Trade(s)
    print(str(dt.datetime.now(est)) + "  " + timeframe + " Update Function Completed.\n")
  else:
    print("Is not time to trade. Cannot open new positions.")


# This function places a market order in the direction BuySell, "B" = Buy, "S" = Sell, uses symbol, amount, stop, limit
def enter(BuySell):
  direction = True;
  if BuySell == "S":
    direction = False;
  try:
    opentrade = con.open_trade(symbol=symbol, is_buy=direction, amount=amount, time_in_force='GTC', order_type='AtMarket', is_in_pips=True, limit=limit, stop=stop)
  except:
    print("Error Opening Trade.")
  else:
    print("Trade Opened Successfully.")


# This function closes all positions that are in the direction BuySell, "B" = Close All Buy Positions, "S" = Close All Sell Positions, uses symbol
def exit(position):
  if position['currency'] == symbol:
    print("Closing tradeID: " + position['tradeId'])
    try:
      closetrade = con.close_trade(trade_id=position['tradeId'], amount=position['amountK'])
    except:
      print("Error Closing Trade.")
    else:
      print("Trade Closed Successfully.")

def print_postion(df):
  print(df.loc[:, ['tradeId','amountK', 'currency', 'open', 'visiblePL', 'isBuy', 'limit_index']])

def print_color(msg, pos_neg):
  sys.stdout.write(RESET)
  print("")
  print("* * * "+ msg+" * * *")
  if pos_neg:
    if pos_neg < 0:
      sys.stdout.write(RED)
    elif pos_neg > 0:
      sys.stdout.write(GREEN)
    elif pos_neg == 0:
      sys.stdout.write(BLUE)

# Returns number of Open Positions for symbol in the direction BuySell, returns total number of both Buy and Sell positions if no direction is specified
def countOpenTrades(BuySell=None):
  openpositions = con.get_open_positions(kind='list')
  isbuy = True
  counter = 0
  if BuySell == "S":
    isbuy = False
  for position in openpositions:
    if position['currency'] == symbol:
      if BuySell is None or position['isBuy'] == isbuy:
        counter+=1
  return counter

def openPositions():
  return con.get_open_positions()


# Return True if current local time is between starttime and endtime
def isTradingTime():
  currenttime = dt.datetime.now(est)
  starttimeconverted = dt.datetime.strptime(starttime, '%H:%M:%S').time()
  endtimeconverted = dt.datetime.strptime(endtime, '%H:%M:%S').time()

  starttimetoday = est.localize(dt.datetime(currenttime.year, currenttime.month, currenttime.day, starttimeconverted.hour, starttimeconverted.minute, starttimeconverted.second))
  endtimetoday = est.localize(dt.datetime(currenttime.year, currenttime.month, currenttime.day, endtimeconverted.hour, endtimeconverted.minute, endtimeconverted.second))

  weekdays = currenttime.weekday()

  if weekdays >= 4:
    print(currenttime, endtimetoday)
    if weekdays == 4 and currenttime < endtimetoday:
      return True
    if weekdays == 6 and currenttime > starttimetoday:
      return True
    return False
  return True
  # #compare current time
  # if starttimetoday <= endtimetoday:
  #   if currenttime >= starttimetoday and currenttime < endtimetoday:
  #     return True
  # else:
  #   if currenttime >= starttimetoday or currenttime < endtimetoday:
  #     return True
  # return False

if isTradingTime():
  Prepare() # Initialize strategy
  StrategyHeartBeat() # Run strategy