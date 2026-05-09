FROM freqtradeorg/freqtrade:stable

# Copy config and strategy
COPY ./config.json /freqtrade/user_data/config.json
COPY ./APEXStrategy.py /freqtrade/user_data/strategies/APEXStrategy.py

# Run freqtrade
CMD ["trade", "--config", "/freqtrade/user_data/config.json", "--strategy", "APEXStrategy"]
