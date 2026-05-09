FROM freqtradeorg/freqtrade:stable

# Copy config.json (must exist at repo root)
COPY ./config.json /freqtrade/user_data/config.json

# Copy the strategy file directly to the strategies directory
COPY ./APEXStrategy.py /freqtrade/user_data/strategies/APEXStrategy.py

# Run freqtrade – ENTRYPOINT already includes "freqtrade"
CMD ["trade", "--config", "/freqtrade/user_data/config.json", "--strategy", "APEXStrategy"]