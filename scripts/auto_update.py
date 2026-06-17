#!/usr/bin/env python3
"""
APAC Trade Compliance - Regulation Auto-Update Script
Checks official sources for new regulations and updates index.html

Sources:
1. GACC (海关总署) - customs.gov.cn announcements
2. TCTC (关税税则委员会) - gss.mof.gov.cn
3. MOFCOM (商务部) - mofcom.gov.cn
4. STA (国家税务总局) - fgk.chinatax.gov.cn
5. Gov.cn (国务院) - gov.cn
"""

import re
import json
import sys
import os
import time
import hashlib
from datetime import datetime, date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INDEX_HTML = os.path.join(os.path.dirname(__file__), '..', 'index.html')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}
TIMEOUT = 30
CURRENT_YEAR = datetime.now().year

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def fetch(url, retries=2):
    """Fetch a URL with retry logic."""
    for i in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            return resp
        except Exception as e:
            if i == retries:
                print(f"  [ERROR] Failed to fetch {url}: {e}")
                return None
            time.sleep(2)

def extract_existing_ids(html_content):
    """Extract existing regulation IDs from index.html."""
    ids = set(re.findall(r'id:\s*["\']([^"\']+)["\']', html_content))
    return ids

def extract_existing_numberCNs(html_content):
    """Extract existing regulation numberCNs from index.html."""
    numberCNs = set(re.findall(r'numberCN:\s*["\']([^"\']+)["\']', html_content))
    return numberCNs

def category_for_keyword(title, desc=""):
    """Determine category based on title and description keywords."""
    text = (title + " " + desc).lower()
    
    # Export Tax Refund
    if any(k in text for k in ['出口退税', '退税率', '免抵退税', '出口货物劳务增值', '消费税政策']):
        return ('Export Tax Refund', '出口退税')
    
    # Export Control
    if any(k in text for k in ['出口管制', '两用物项', '出口许可', '出口申报', '出口配额',
                                '无人机', '车床', '铣床', '磨床', '物项出口']):
        return ('Export Control', '出口管制')
    
    # AEO / Enterprise
    if any(k in text for k in ['高级认证', 'aeo', '企业信用', '企业注册', '注册管理',
                                '注册登记', '备案企业', '认证企业', '简易复核',
                                '境外生产企业注册']):
        return ('AEO / Enterprise', '企业管理')
    
    # Bonded / FTZ
    if any(k in text for k in ['保税', '自贸区', '自贸港', '零关税进境', '综合保税',
                                '跨境区', '离岛免税']):
        return ('Bonded / FTZ', '保税/自贸区')
    
    # Tariff
    if any(k in text for k in ['关税', '税则', '税率', '暂定税率', '协定税率',
                                '零关税', '进口税收', '加征关税', '关税调整',
                                '原产地管理', '原产地规则', '优惠原产地',
                                '电子信息联网', '科技创新进口']):
        return ('Tariff', '关税税率')
    
    # Inspection & Quarantine
    if any(k in text for k in ['检验检疫', '商品检验', '卫生检疫', '动植物检疫',
                                '检疫', '抽查检验', '检验采信', '外来物种',
                                '指定监管场地', '进口食品', '化妆品检验',
                                '检验检测', '监管场地']):
        return ('Inspection & Quarantine', '检验检疫')
    
    # Customs Supervision (default for GACC)
    return ('Customs Supervision', '监管通关')

def org_for_source(source_url, title=""):
    """Determine org and source from the URL and title."""
    if 'gss.mof.gov.cn' in source_url:
        return ('TCTC', '关税税则委员会', 'TCTC')
    if 'mofcom.gov.cn' in source_url:
        return ('MOFCOM', '商务部', 'MOFCOM')
    if 'chinatax.gov.cn' in source_url:
        return ('STA', '国家税务总局', 'STA')
    if 'gov.cn' in source_url:
        return ('SCIO', '国务院', 'Gov.cn')
    if 'customs.gov.cn' in source_url:
        return ('GACC', '海关总署', 'GACC')
    return ('GACC', '海关总署', 'GACC')

def build_regulation_entry(reg_data):
    """Build a JS object string for a new regulation."""
    lines = []
    lines.append(f'  {{')
    lines.append(f'    id: "{reg_data["id"]}",')
    lines.append(f'    number: "{reg_data["number"]}",')
    lines.append(f'    numberCN: "{reg_data["numberCN"]}",')
    lines.append(f'    title: "{reg_data["title"]}",')
    lines.append(f'    date: "{reg_data["date"]}",')
    lines.append(f'    effectiveDate: "{reg_data["effectiveDate"]}",')
    lines.append(f'    org: "{reg_data["org"]}",')
    lines.append(f'    orgCN: "{reg_data["orgCN"]}",')
    lines.append(f'    category: "{reg_data["category"]}",')
    lines.append(f'    categoryCN: "{reg_data["categoryCN"]}",')
    lines.append(f'    status: "{reg_data["status"]}",')
    # Escape quotes in description
    desc = reg_data.get("description", "").replace('"', '\\"')
    lines.append(f'    description: "{desc}",')
    lines.append(f'    supersedes: [],')
    lines.append(f'    supersededDetails: [],')
    lines.append(f'    url: "{reg_data["url"]}",')
    lines.append(f'    source: "{reg_data["source"]}"')
    lines.append(f'  }}')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Source scrapers
# ---------------------------------------------------------------------------

def scrape_gacc_announcements():
    """Scrape GACC announcement listing page for 2026 regulations."""
    new_regs = []
    print("[GACC] Checking customs.gov.cn for new announcements...")
    
    # GACC announcement listing page
    url = "http://www.customs.gov.cn/customs/302249/2480148/index.html"
    resp = fetch(url)
    if not resp:
        print("  [GACC] Failed to fetch listing page")
        return new_regs
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Find announcement links
    links = soup.find_all('a', href=True)
    for link in links:
        href = link.get('href', '')
        title = link.get_text(strip=True)
        
        # Only look for 2026 announcements
        if '2026' not in title and '2026' not in href:
            continue
        
        # Match pattern like "海关总署公告2026年第XX号"
        match = re.search(r'公告2026年第(\d+)号', title)
        if not match:
            continue
        
        ann_num = match.group(1)
        full_url = urljoin(url, href)
        
        new_regs.append({
            'source_type': 'GACC',
            'numberCN': f'海关总署公告2026年第{ann_num}号',
            'title_raw': title,
            'url': full_url,
            'ann_num': ann_num,
        })
    
    print(f"  [GACC] Found {len(new_regs)} potential announcements")
    return new_regs


def scrape_tctc_announcements():
    """Scrape TCTC (关税税则委员会) policy releases."""
    new_regs = []
    print("[TCTC] Checking gss.mof.gov.cn for new policies...")
    
    url = "http://gss.mof.gov.cn/gzdt/zhengcefabu/"
    resp = fetch(url)
    if not resp:
        print("  [TCTC] Failed to fetch listing page")
        return new_regs
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        title = link.get_text(strip=True)
        
        if '2026' not in title and '2026' not in href:
            continue
        
        # Match TCTC announcement patterns
        match = re.search(r'税委会(?:公告|通知)2026年第(\d+)号', title)
        if not match:
            # Also check for other TCTC patterns
            match = re.search(r'财关税〔2026〕(\d+)号', title)
        
        if match:
            full_url = urljoin(url, href)
            new_regs.append({
                'source_type': 'TCTC',
                'numberCN_raw': title,
                'title_raw': title,
                'url': full_url,
            })
    
    print(f"  [TCTC] Found {len(new_regs)} potential announcements")
    return new_regs


def scrape_mofcom_announcements():
    """Scrape MOFCOM policy releases for trade-related announcements."""
    new_regs = []
    print("[MOFCOM] Checking mofcom.gov.cn for new policies...")
    
    url = "https://www.mofcom.gov.cn/zcfb/index.html"
    resp = fetch(url)
    if not resp:
        print("  [MOFCOM] Failed to fetch listing page")
        return new_regs
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        title = link.get_text(strip=True)
        
        # Only look for trade/customs related announcements
        if not any(k in title for k in ['出口管制', '两用物项', '进出口', '贸易', '关税']):
            continue
        if '2026' not in title:
            continue
        
        full_url = urljoin(url, href)
        new_regs.append({
            'source_type': 'MOFCOM',
            'numberCN_raw': title,
            'title_raw': title,
            'url': full_url,
        })
    
    print(f"  [MOFCOM] Found {len(new_regs)} potential announcements")
    return new_regs


def scrape_sta_announcements():
    """Scrape STA (国家税务总局) for export tax refund related policies."""
    new_regs = []
    print("[STA] Checking fgk.chinatax.gov.cn for new policies...")
    
    url = "https://fgk.chinatax.gov.cn/zcfgk/c100012/c5247423/content.html"
    # STA site is hard to scrape, try the listing page
    list_url = "https://fgk.chinatax.gov.cn/zcfgk/c100012/"
    resp = fetch(list_url)
    if not resp:
        print("  [STA] Failed to fetch listing page")
        return new_regs
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        title = link.get_text(strip=True)
        
        if not any(k in title for k in ['出口', '退税', '增值税', '消费税']):
            continue
        if '2026' not in title:
            continue
        
        full_url = urljoin(list_url, href)
        new_regs.append({
            'source_type': 'STA',
            'numberCN_raw': title,
            'title_raw': title,
            'url': full_url,
        })
    
    print(f"  [STA] Found {len(new_regs)} potential announcements")
    return new_regs


# ---------------------------------------------------------------------------
# Main update logic
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"APAC Trade Compliance - Auto Update Check")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Read current index.html
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    existing_ids = extract_existing_ids(html_content)
    existing_numberCNs = extract_existing_numberCNs(html_content)
    print(f"\nExisting regulations: {len(existing_ids)} entries")
    print(f"Existing numberCNs: {len(existing_numberCNs)} entries")
    
    # Scrape all sources
    all_new = []
    all_new.extend(scrape_gacc_announcements())
    all_new.extend(scrape_tctc_announcements())
    all_new.extend(scrape_mofcom_announcements())
    all_new.extend(scrape_sta_announcements())
    
    # Filter out already-existing regulations
    truly_new = []
    for reg in all_new:
        numberCN = reg.get('numberCN', reg.get('numberCN_raw', ''))
        if numberCN and numberCN in existing_numberCNs:
            continue
        truly_new.append(reg)
    
    print(f"\n{'=' * 60}")
    print(f"Total found: {len(all_new)}, New: {len(truly_new)}")
    
    if not truly_new:
        print("No new regulations found. Exiting.")
        return False
    
    # For each new regulation, we need more details
    # Since scraping detail pages is unreliable, we'll create placeholder entries
    # that will need manual review
    print(f"\nNew regulations detected:")
    for reg in truly_new:
        print(f"  - {reg.get('numberCN', reg.get('numberCN_raw', 'UNKNOWN'))}")
        print(f"    URL: {reg['url']}")
        print(f"    Source: {reg['source_type']}")
    
    # Create a notification file for manual review
    notification = {
        "timestamp": datetime.now().isoformat(),
        "new_regulations": truly_new,
        "action_required": "Please review and add these regulations to the tracker"
    }
    
    notif_path = os.path.join(os.path.dirname(__file__), '..', 'new_regulations.json')
    with open(notif_path, 'w', encoding='utf-8') as f:
        json.dump(notification, f, ensure_ascii=False, indent=2)
    
    print(f"\nNotification saved to new_regulations.json")
    print("⚠️ New regulations require manual review before adding to the tracker.")
    print("Government website scraping is unreliable; manual verification is essential.")
    
    return True


if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        has_updates = main()
        sys.exit(0 if has_updates else 0)
    except Exception as e:
        print(f"[FATAL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
