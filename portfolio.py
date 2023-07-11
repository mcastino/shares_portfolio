import pandas as pd
import os
from dotenv import load_dotenv
import yfinance as yf
import requests
import streamlit as st
from datetime import datetime, timedelta
import altair as alt
import streamlit_authenticator as stauth
from streamlit_authenticator import Authenticate
import yaml
from yaml.loader import SafeLoader

def show_website():
  # Connect to Airtable.
  load_dotenv()
  api_key = st.secrets["api_key"]
  base_id = 'appFdhFr1tPBm1yjW'
  table_name = 'fact_transactions'
  url = f'https://api.airtable.com/v0/{base_id}/{table_name}'
  headers = {'Authorization': f'Bearer {api_key}'}
  response = requests.get(url, headers=headers)
  data = response.json()

  ### TRANSACTIONS ###

  # Extract the records from the response and create DataFrame
  records = data['records']
  rows = []
  for record in records:
    fields = record['fields']
    rows.append(fields)
  df_txn = pd.DataFrame(rows)
  df_txn = df_txn[['date', 'action', 'account', 'market', 'ticker', 'units', 'price', 'brokerage', 'net_total', 'effective_price']]
  df_txn.columns = ['Trade Date', 'Action', 'Account', 'Market', 'Ticker', 'Units', 'Price', 'Brokerage', 'Net Total', 'Effective Price']
  # Calculate most recent price for each stock
  df_txn['Current Price'] = (df_txn['Ticker'] + '.AX').apply(lambda ticker: yf.Ticker(ticker).history(period='1d')['Close'].iloc[-1] if yf.Ticker(ticker).history(period='1d')['Close'].shape[0] > 0 else None)

  #Create list of unique stocks from transactions table
  stocks = (df_txn['Ticker'] + '.AX').unique().tolist()

  ### PORTFOLIO SUMMARY ###
  df_list = []

  for stock in stocks:
    ticker_data_p = yf.Ticker(stock)
    df_history = pd.DataFrame(ticker_data_p.history(period='1d', start=df_txn['Trade Date'].min(), end=datetime.now())).reset_index()
    df_history['Ticker'] = stock.split('.')[0]
    df_list.append(df_history)

  df_close = pd.concat(df_list)

  df_portfolio = pd.merge(df_close[['Date', 'Close', 'Ticker']],
                          df_txn[['Trade Date', 'Ticker', 'Units', 'Price', 'Brokerage', 'Net Total']], 
                          left_on = 'Ticker', 
                          right_on = 'Ticker', 
                          how = 'left')
  df_portfolio = df_portfolio[df_portfolio['Trade Date'] <= df_portfolio['Date']]
  df_portfolio.sort_values(by = 'Date', ascending = True, inplace = True)
  df_portfolio.reset_index(inplace=True)



  df_portfolio['Close Value'] = df_portfolio['Close'] * df_portfolio['Units']
  df_portfolio['Delta'] = df_portfolio['Close Value'] - df_portfolio['Net Total']

  df_portfolio_summary = df_portfolio.groupby('Date')[['Delta','Net Total','Brokerage']].sum().reset_index()
  df_portfolio_by_ticker = df_portfolio.groupby(['Date', 'Ticker'])[['Delta','Net Total','Brokerage']].sum().reset_index()
  df_portfolio_summary.columns = ['Date', 'Profit', 'Total Invested', 'Brokerage Paid']

  # current position
  current_position = df_portfolio_summary['Profit'].iloc[-1]
  total_invested = df_portfolio_summary['Total Invested'].iloc[-1]
  current_position_perc = current_position / total_invested * 100
  brokerage = df_portfolio_summary['Brokerage Paid'].iloc[-1]

  st.subheader('Current Position')
  col1, col2, col3 = st.columns([33.3, 33.3, 33.3])
  col1.metric('Net Position', '$' + str(round(current_position, 2)), delta = str(round(current_position_perc, 2)) + '%', delta_color='normal')
  col2.metric('Amount Invested', '$' + str(round(total_invested, 2)))
  col3.metric('Brokerage Paid', '$' + str(round(brokerage, 2)))
  st.divider()  # 👈 Draws a horizontal rule

  # position over time
  y_min_p = df_portfolio_summary.Profit.min()
  y_max_p = df_portfolio_summary.Profit.max()
  y_padding_p = (y_max_p - y_min_p) * 0.1  # Adjust padding as needed
  y_range_p = [y_min_p - y_padding_p, y_max_p + y_padding_p]

  # Create the Altair chart with the specified y-axis range
  chart_p = alt.Chart(df_portfolio_summary).mark_line().encode(
      x='Date',
      y='Profit'
  ).properties(
      height=500,
      width = 'container'
  ).configure_axis(
      grid=False
  ).configure_view(
      strokeWidth=0
  ).configure_title(
      fontSize=20
  ).configure_legend(
      title=None
  ).configure_header(
      titleOrient='bottom'
  )
  chart_p = chart_p.encode(alt.Y('Profit', scale=alt.Scale(domain=y_range_p)))
  st.subheader('Portfolio Over Time')
  st.altair_chart(chart_p)

  # portfolio breakdown by ticker
  most_recent_date = df_portfolio['Date'].max()
  df_filtered = df_portfolio[df_portfolio['Date'] == most_recent_date]

  df_grouped = df_filtered.groupby('Ticker')['Net Total'].sum().reset_index()

  st.divider()  # 👈 Draws a horizontal rule
  st.subheader('Portfolio By Ticker')

  df_pivot = df_portfolio_by_ticker.pivot(index='Date', columns='Ticker', values='Delta')

  st.line_chart(df_pivot, height = 500)


  st.divider()  # 👈 Draws a horizontal rule

  st.subheader('Portfolio Composition')
  # Create the bar chart using Streamlit
  st.bar_chart(df_grouped.set_index('Ticker'))



  ### MARKET SUMMARY ###

  st.divider()  # 👈 Draws a horizontal rule

  st.subheader('Market Summary')

  #Radio Button for Selecting Time Range on App
  st.write('<style>div.row-widget.stRadio > div{flex-direction:row;justify-content: left;} </style>', unsafe_allow_html=True)
  st.write('<style>div.st-bf{flex-direction:column;} div.st-ag{padding-left:2px;}</style>', unsafe_allow_html=True)
  period=st.radio("Period",('1W', '1M','6M', 'YTD','1Y', '2Y', '5Y'),index=3)

  #Use input from radio button to determine start time of graph.
  end = datetime.now()
  if period == '1W':
    start = (datetime.now() - timedelta(days= 7))
  elif period == '1M':
    start = (datetime.now() - timedelta(days= 28))
  elif period == '6M':
    start = (datetime.now() - timedelta(days= 0.5 * 365)) 
  elif period == 'YTD':
    start = datetime.now().date().replace(month=1, day=1)
  else:
    start = (datetime.now() - timedelta(days= int(period[0]) * 365))  

  df_list = []

  for stock in stocks:
    st.title(stock.split('.')[0])
    ticker_data = yf.Ticker(stock)
    ticker_df = pd.DataFrame(ticker_data.history(period='1d', start=start, end=end)).reset_index()
    df_list.append(ticker_df)

    # Determine the y-axis range based on the data
    y_min = ticker_df.Close.min()
    y_max = ticker_df.Close.max()
    y_padding = (y_max - y_min) * 0.1  # Adjust padding as needed
    y_range = [y_min - y_padding, y_max + y_padding]
    
    # Create the Altair chart with the specified y-axis range
    chart = alt.Chart(ticker_df).mark_line().encode(
        x='Date',
        y='Close'
    ).properties(
        height=400,
        width = 'container'
    ).configure_axis(
        grid=False
    ).configure_view(
        strokeWidth=0
    ).configure_title(
        fontSize=20
    ).configure_legend(
        title=None
    ).configure_header(
        titleOrient='bottom'
    )
    chart = chart.encode(alt.Y('Close', scale=alt.Scale(domain=y_range)))
    st.altair_chart(chart)

  st.divider()  # 👈 Draws a horizontal rule

  ### TRANSACTION SUMMARY###
  st.subheader('Transactions')
  st.dataframe(df_txn)

#Logic for login#
with open('credentials.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)
name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status:
    authenticator.logout('Logout', 'main')
    st.write(f'Welcome *{name}*')
    show_website()
elif authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your username and password')





