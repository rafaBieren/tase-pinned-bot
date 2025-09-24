"""
Alternative data source for Israeli indices using web scraping.
This module provides a fallback when Yahoo Finance rate limiting is too aggressive.
"""

import requests
from bs4 import BeautifulSoup
import re
from typing import Optional, Dict
from loguru import logger


def scrape_investing_indices() -> Dict[str, Dict[str, float]]:
    """
    Scrape Israeli indices data from Investing.com as a fallback.
    Returns a dictionary with index data.
    """
    try:
        # Investing.com Israeli indices page
        url = "https://www.investing.com/indices/israel-indices"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the indices table
        indices_data = {}
        
        # Look for specific indices in the page
        # This is a simplified approach - in production you'd need more robust parsing
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 3:
                name_cell = cells[0].get_text(strip=True)
                price_cell = cells[1].get_text(strip=True)
                change_cell = cells[2].get_text(strip=True)
                
                # Look for Israeli indices
                if any(index in name_cell.upper() for index in ['TA-35', 'TA-125', 'TA-90', 'BANKS']):
                    try:
                        # Extract price (remove commas and convert to float)
                        price = float(price_cell.replace(',', ''))
                        
                        # Extract percentage change
                        change_pct = 0.0
                        if change_cell and change_cell != '-':
                            change_pct = float(change_cell.replace('%', '').replace('+', ''))
                        
                        # Calculate previous close
                        prev_close = price / (1 + change_pct / 100) if change_pct != 0 else price
                        
                        indices_data[name_cell] = {
                            'price': price,
                            'prev_close': prev_close,
                            'change_pct': change_pct
                        }
                        
                        logger.info(f"Scraped {name_cell}: {price} ({change_pct:+.2f}%)")
                        
                    except (ValueError, ZeroDivisionError) as e:
                        logger.warning(f"Failed to parse data for {name_cell}: {e}")
                        continue
        
        return indices_data
        
    except Exception as e:
        logger.error(f"Failed to scrape Investing.com data: {e}")
        return {}


def get_index_data_from_alternative_source(index_name: str) -> Optional[Dict[str, float]]:
    """
    Get data for a specific index from alternative sources.
    """
    try:
        # Try Investing.com first
        data = scrape_investing_indices()
        
        # Look for the specific index
        for name, values in data.items():
            if index_name.upper() in name.upper():
                return values
        
        # If not found, try other sources or return None
        return None
        
    except Exception as e:
        logger.error(f"Failed to get alternative data for {index_name}: {e}")
        return None
