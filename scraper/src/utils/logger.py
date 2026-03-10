import logging
import sys

COLORS = {
    'DEBUG': '\033[94m',
    'INFO': '\033[92m',
    'WARNING': '\033[93m',
    'ERROR': '\033[91m',
    'CRITICAL': '\033[1;91m',
    'RESET': '\033[0m',
    'NAME': '\033[36m'
}

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        # Set color based on log level
        level_color = COLORS.get(record.levelname, COLORS['RESET'])
        colored_levelname = f"{level_color}{record.levelname}{COLORS['RESET']}"
        colored_name = f"{COLORS['NAME']}[{record.name}]{COLORS['RESET']}"
        
        # Format the message with colors
        record.levelname = colored_levelname
        record.name = colored_name
        
        return super().format(record)

def get_logger(name: str = "system") -> logging.Logger:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO) # Console only outputs INFO or higher
        
        # Time | Level | [Name] | Message format
        formatter = ColoredFormatter(
            fmt="%(asctime)s | %(levelname)-14s | %(name)-12s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        logging.getLogger("httpx").setLevel(logging.WARNING)
        
    return logger

def log_progress(logger, current: int, total: int, prefix: str = "Progress", bar_length: int = 20):
    if total == 0:
        return

    percent = (current / total) * 100
    filled_length = int(bar_length * current // total)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)

    logger.info(f"{prefix} |{bar}| {percent:.1f}% ({current}/{total})")