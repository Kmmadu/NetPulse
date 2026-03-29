#!/usr/bin/env python3
"""
Structured Logging
NetPulse Network Monitoring System
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from typing import Optional
from .config import config


class StructuredLogger:
    """Structured logging with context"""
    
    def __init__(self, name: str = "netpulse"):
        self.logger = logging.getLogger(name)
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure logging based on config"""
        self.logger.setLevel(getattr(logging, config.logging.level))
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(
            config.logging.format,
            datefmt=config.logging.date_format
        ))
        self.logger.addHandler(console_handler)
        
        # File handler (if configured)
        if config.logging.file:
            os.makedirs(os.path.dirname(config.logging.file), exist_ok=True)
            file_handler = RotatingFileHandler(
                config.logging.file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setFormatter(logging.Formatter(
                config.logging.format,
                datefmt=config.logging.date_format
            ))
            self.logger.addHandler(file_handler)
    
    def info(self, msg: str, **kwargs):
        """Log info with context"""
        if kwargs:
            msg = f"{msg} | {kwargs}"
        self.logger.info(msg)
    
    def warning(self, msg: str, **kwargs):
        """Log warning with context"""
        if kwargs:
            msg = f"{msg} | {kwargs}"
        self.logger.warning(msg)
    
    def error(self, msg: str, **kwargs):
        """Log error with context"""
        if kwargs:
            msg = f"{msg} | {kwargs}"
        self.logger.error(msg)
    
    def debug(self, msg: str, **kwargs):
        """Log debug with context"""
        if kwargs:
            msg = f"{msg} | {kwargs}"
        self.logger.debug(msg)
    
    def exception(self, msg: str, **kwargs):
        """Log exception with traceback"""
        if kwargs:
            msg = f"{msg} | {kwargs}"
        self.logger.exception(msg)


# Global logger instance
logger = StructuredLogger()