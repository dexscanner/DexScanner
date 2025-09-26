import time
import logging
import os
from tokens import process_tokens

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(DATA_DIR, "token_alerts.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

if __name__ == "__main__":
    logging.info("Starting continuous token watcher...")
    try:
        while True:
            process_tokens()
            logging.info("Sleeping for 60s...")
            time.sleep(60)   # safer, matches API rate limit
    except KeyboardInterrupt:
        logging.info("Shutting down gracefully...")