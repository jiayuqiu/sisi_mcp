import logging


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger with a format that includes filename and line number.

    Usage:
        from mcp_conductor.resources.utils.logger import get_logger
        logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.propagate = False

    return logger
