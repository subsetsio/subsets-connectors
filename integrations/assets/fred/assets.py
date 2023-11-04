import requests
import os
from dagster import asset
import pandas as pd
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

@sleep_and_retry
@limits(calls=100, period=60)
@retry(wait=wait_exponential(multiplier=2), stop=stop_after_attempt(5), reraise=True)
def make_request(url):
    response = requests.get(url)
    response.raise_for_status() 
    return response.json()

def get_child_categories(category_id, api_key):
    url = f"https://api.stlouisfed.org/fred/category/children?category_id={category_id}&file_type=json&api_key={api_key}"
    return make_request(url)['categories']

def get_series_info(api_key, category_id):
    url = f"https://api.stlouisfed.org/fred/category/series?category_id={category_id}&api_key={api_key}&file_type=json"
    return pd.DataFrame(make_request(url)['seriess'])

def get_series_observations(series_id, api_key):
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json"
    df = pd.DataFrame(make_request(url)['observations'])[['date', 'value']]
    df['id'] = series_id
    return df

def get_category_tree(category_id, api_key):
    child_categories = get_child_categories(category_id, api_key)
    return child_categories + [item for child in child_categories for item in get_category_tree(child['id'], api_key)]

@asset
def fred_category_tree() -> pd.DataFrame:
    api_key = os.getenv("FRED_API_KEY")
    categories = get_category_tree('0', api_key)
    return pd.DataFrame(categories, columns=["id", "name", "parent_id"])


@asset 
def fred_categories(fred_category_tree: pd.DataFrame) -> pd.DataFrame:
    ids = fred_category_tree['id'].unique()
    categories = [get_series_info(os.getenv("FRED_API_KEY"), category_id) for category_id in ids]
    return pd.concat(categories, ignore_index=True)

@asset(metadata={
    "source": "fred",
    "name": "Federal Reserve Economic Data",
    "description": "Dataset with time series from the Federal Reserve Economic Data (FRED) API.",
})
def fred_series(fred_categories: pd.DataFrame) -> pd.DataFrame:
    ids = fred_categories['id'].unique()
    series = [get_series_observations(series_id, os.getenv("FRED_API_KEY")) for series_id in ids]
    return pd.concat(series, ignore_index=True)