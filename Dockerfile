FROM freqtradeorg/freqtrade:stable

# Copy your config file (now named config.json)
COPY ./config.json /freqtrade/user_data/config.json

# Copy your strategy folder
COPY ./strategies /freqtrade/user_data/strategies

# Run freqtrade with the correct config
CMD ["freqtrade", "trade", "--config", "/freqtrade/user_data/config.json", "--strategy", "APEXStrategy"]