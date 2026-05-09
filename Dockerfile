FROM freqtradeorg/freqtrade:stable

COPY ./APEXStrategy.py /freqtrade/user_data/strategies/APEXStrategy.py
COPY ./freqtrade_config.json /freqtrade/user_data/config.json

CMD ["trade", "--config", "/freqtrade/user_data/config.json", "--strategy", "APEXStrategy"]