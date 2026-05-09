FROM freqtradeorg/freqtrade:stable

# Copy our strategy
COPY APEXStrategy.py /freqtrade/user_data/strategies/APEXStrategy.py

# Copy our config
COPY freqtrade_config.json /freqtrade/user_data/config.json

# Run in dry-run (paper) mode
CMD ["trade", \
     "--config", "/freqtrade/user_data/config.json", \
     "--strategy", "APEXStrategy", \
     "--dry-run"]
