"""
Script to download OWID CO2 data.
"""
import os
import requests
import sys
from pathlib import Path

def download_owid_data():
    """Download OWID CO2 data from GitHub."""
    url = "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"
    
    # Get script directory and project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Create data directory if it doesn't exist
    data_dir = project_root / 'data'
    data_dir.mkdir(exist_ok=True)
    
    output_path = data_dir / 'owid-co2-data.csv'
    
    print(f"Downloading OWID CO2 data from {url}...")
    print(f"Output path: {output_path}")
    
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rProgress: {percent:.1f}%", end='', flush=True)
        
        print(f"\n✓ Successfully downloaded {downloaded / (1024*1024):.2f} MB")
        print(f"✓ Data saved to: {output_path}")
        return True
        
    except Exception as e:
        print(f"\n✗ Error downloading data: {str(e)}")
        return False

if __name__ == "__main__":
    download_owid_data()

