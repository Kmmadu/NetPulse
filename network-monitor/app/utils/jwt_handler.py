#!/usr/bin/env python3
"""
JWT Token Handler for NetPulse
"""

import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
import os

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-change-this-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24  # Token expires in 24 hours


def create_access_token(data: Dict) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Dictionary with user information (user_id, username)
    
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({'exp': expire})
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[Dict]:
    """
    Verify and decode JWT token
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        print("[JWT] Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"[JWT] Invalid token: {e}")
        return None


def get_user_id_from_token(token: str) -> Optional[int]:
    """
    Extract user_id from JWT token
    
    Args:
        token: JWT token string
    
    Returns:
        user_id if valid, None otherwise
    """
    payload = verify_token(token)
    if payload:
        return payload.get('user_id')
    return None