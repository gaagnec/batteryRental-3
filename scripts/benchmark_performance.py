"""
Performance Testing Script for Battery Rental Admin
Run this to measure current performance metrics
"""

import time
import requests
from collections import defaultdict

# Site URL
BASE_URL = "https://batteryrental-3.onrender.com"

# Pages to test
PAGES = {
    "Admin Index": "/admin/",
    "Dashboard": "/admin/dashboard/",
    "Clients": "/admin/rental/client/",
    "Rentals": "/admin/rental/rental/",
    "Payments": "/admin/rental/payment/",
}

def measure_page_load(url, session=None):
    """Measure page load time"""
    if session:
        start = time.time()
        response = session.get(url)
        load_time = time.time() - start
    else:
        start = time.time()
        response = requests.get(url, allow_redirects=True)
        load_time = time.time() - start
    
    return {
        'status_code': response.status_code,
        'load_time': round(load_time, 2),
        'size': len(response.content),
        'size_kb': round(len(response.content) / 1024, 2),
    }

def run_benchmarks():
    """Run all performance benchmarks"""
    print("=" * 60)
    print("🔍 PERFORMANCE BENCHMARK - Battery Rental Admin")
    print("=" * 60)
    print(f"\nTesting URL: {BASE_URL}")
    print(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n" + "-" * 60)
    
    # Test each page (3 runs each for average)
    results = defaultdict(list)
    
    for page_name, page_url in PAGES.items():
        print(f"\n📄 Testing: {page_name}")
        full_url = BASE_URL + page_url
        
        for run in range(3):
            try:
                result = measure_page_load(full_url)
                results[page_name].append(result)
                print(f"  Run {run+1}: {result['load_time']}s | "
                      f"{result['size_kb']}KB | "
                      f"Status: {result['status_code']}")
                time.sleep(0.5)  # Small delay between runs
            except Exception as e:
                print(f"  Run {run+1}: ERROR - {e}")
    
    # Calculate averages
    print("\n" + "=" * 60)
    print("📊 AVERAGE RESULTS")
    print("=" * 60)
    print(f"\n{'Page':<20} {'Avg Load Time':<15} {'Avg Size':<15} {'Status'}")
    print("-" * 60)
    
    for page_name, runs in results.items():
        if runs:
            avg_time = sum(r['load_time'] for r in runs) / len(runs)
            avg_size = sum(r['size_kb'] for r in runs) / len(runs)
            status = runs[0]['status_code']
            print(f"{page_name:<20} {avg_time:<15.2f}s {avg_size:<15.2f}KB {status}")
    
    print("\n" + "=" * 60)
    print("✅ Benchmark Complete!")
    print("=" * 60)
    
    return results

if __name__ == "__main__":
    run_benchmarks()

