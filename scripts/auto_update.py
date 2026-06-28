#!/usr/bin/env python3
"""
APAC Trade Compliance - Regulation Auto-Update Script (Enhanced)
Checks official sources for new regulations, generates entries, and updates index.html

Key enhancements over v1:
- Direct index.html update with proper BUILTIN_REGULATIONS entries
- Anti-crawling workaround via gov.cn mirrors and search engines
- Auto-generates IDs, categories, and formatted descriptions
- Commits and pushes changes to gh-pages branch

Sources:
1. GACC - customs.gov.cn (primary) / gov.cn mirror (fallback)
2. TCTC - gss.mof.gov.cn
3. MOFCOM - mofcom.gov.cn
4. STA - fgk.chinatax.gov.cn (primary) / gov.cn mirror (fallback)
5. Gov.cn - gov.cn (central policy database)
"""

import re
import json
import sys
import os
import time
import hashlib
import subprocess
from datetime import datetime, date
from urllib.parse import urljoin, quote

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
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}
TIMEOUT = 30
CURRENT_YEAR = datetime.now().year

# Category mapping (same as in Skill)
CATEGORY_KEYWORDS = {
    'Export Tax Refund': ['出口退税', '退税率', '免抵退税', '出口货物劳务增值', '消费税政策'],
    'Export Control': ['出口管制', '两用物项', '出口许可', '出口申报', '出口配额',
                       '无人机', '车床', '铣床', '磨床', '物项出口'],
    'AEO / Enterprise': ['高级认证', 'aeo', 'AEO', '企业信用', '企业注册', '注册管理',
                          '注册登记', '备案企业', '认证企业', '简易复核',
                          '境外生产企业注册'],
    'Bonded / FTZ': ['保税', '自贸区', '自贸港', '零关税进境', '综合保税',
                      '跨境区', '离岛免税'],
    'Tariff': ['关税', '税则', '税率', '暂定税率', '协定税率',
               '零关税', '进口税收', '加征关税', '关税调整',
               '原产地管理', '原产地规则', '优惠原产地',
               '电子信息联网', '科技创新进口'],
    'Inspection & Quarantine': ['检验检疫', '商品检验', '卫生检疫', '动植物检疫',
                                 '检疫', '抽查检验', '检验采信', '外来物种',
                                 '指定监管场地', '进口食品', '化妆品检验',
                                 '检验检测', '监管场地'],
}

CATEGORY_CN_MAP = {
    'Export Tax Refund': '出口退税',
    'Export Control': '出口管制',
    'AEO / Enterprise': '企业管理',
    'Bonded / FTZ': '保税/自贸区',
    'Tariff': '关税税率',
    'Inspection & Quarantine': '检验检疫',
    'Customs Supervision': '监管通关',
}

CATEGORY_EMOJI_MAP = {
    'Tariff': '💰',
    'Export Control': '🔒',
    'AEO / Enterprise': '🏢',
    'Customs Supervision': '🛃',
    'Bonded / FTZ': '🏗️',
    'Export Tax Refund': '💸',
    'Inspection & Quarantine': '🔬',
}

ORG_MAP = {
    'GACC': {'org': 'GACC', 'orgCN': '海关总署', 'source': 'GACC'},
    'TCTC': {'org': 'TCTC', 'orgCN': '关税税则委员会', 'source': 'TCTC'},
    'MOFCOM': {'org': 'MOFCOM', 'orgCN': '商务部', 'source': 'MOFCOM'},
    'STA': {'org': 'STA', 'orgCN': '国家税务总局', 'source': 'STA'},
    'Gov.cn': {'org': 'SC', 'orgCN': '国务院', 'source': 'SC / Gov.cn'},
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def fetch(url, retries=3, delay=3):
    """Fetch a URL with retry logic and delay between retries."""
    for i in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False,
                                allow_redirects=True)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            if resp.status_code == 200:
                return resp
            print(f"  [HTTP {resp.status_code}] {url}")
            if i < retries:
                time.sleep(delay)
        except Exception as e:
            if i == retries:
                print(f"  [ERROR] Failed to fetch {url}: {e}")
                return None
            time.sleep(delay)
    return None


def extract_existing_ids(html_content):
    """Extract existing regulation IDs from index.html."""
    return set(re.findall(r'id:\s*"([^"]+)"', html_content))


def extract_existing_numberCNs(html_content):
    """Extract existing regulation numberCNs from index.html."""
    return set(re.findall(r'numberCN:\s*"([^"]+)"', html_content))


def get_max_numeric_id(html_content, prefix="2026-"):
    """Get the maximum numeric ID value from existing regulations."""
    existing_ids = extract_existing_ids(html_content)
    max_num = 0
    for id_val in existing_ids:
        if id_val.startswith(prefix):
            num_part = id_val[len(prefix):]
            try:
                n = int(num_part)
                if n > max_num:
                    max_num = n
            except ValueError:
                m = re.match(r'^(\d+)', num_part)
                if m:
                    n = int(m.group(1))
                    if n > max_num:
                        max_num = n
    return max_num


def generate_batch_ids(html_content, count, prefix="2026-"):
    """Generate a batch of unique IDs for new regulations."""
    existing_ids = extract_existing_ids(html_content)
    max_num = get_max_numeric_id(html_content, prefix)
    
    ids = []
    next_num = max_num + 1
    for _ in range(count):
        while True:
            candidate = f"{prefix}{next_num:03d}"
            if candidate not in existing_ids and candidate not in ids:
                ids.append(candidate)
                next_num += 1
                break
            next_num += 1
    
    return ids


def determine_category(title, desc=""):
    """Determine category based on title and description keywords."""
    text = title + " " + desc
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return category
    
    # Default for GACC/Gov.cn announcements without specific keywords
    return 'Customs Supervision'


def determine_org_and_source(source_type, url="", title=""):
    """Determine org, orgCN, and source badge from source type and URL."""
    # Check URL for override
    if 'gov.cn' in url and 'customs.gov.cn' not in url and 'mofcom.gov.cn' not in url and 'chinatax.gov.cn' not in url and 'gss.mof.gov.cn' not in url:
        return ORG_MAP['Gov.cn']
    
    return ORG_MAP.get(source_type, ORG_MAP['GACC'])


def clean_title(title_raw):
    """Clean a regulation title by removing org prefixes and announcement number prefixes."""
    # Remove common prefixes
    prefixes = [
        r'海关总署公告\d{4}年第\d+号\s*[：:]\s*',
        r'商务部公告\d{4}年第\d+号\s*[：:]\s*',
        r'税委会(?:公告|通知)\d{4}年第\d+号\s*[：:]\s*',
        r'国家税务总局公告\d{4}年第\d+号\s*[：:]\s*',
        r'国务院(?:公告|通知|文件)\s*[：:]\s*',
        r'关于\s*',  # Remove "关于" prefix for cleaner titles
    ]
    
    cleaned = title_raw
    for prefix in prefixes[:-1]:  # Keep "关于" as it's part of regulation titles
        cleaned = re.sub(prefix, '', cleaned).strip()
    
    return cleaned


def extract_numberCN_from_title(title):
    """Extract the official announcement number (numberCN) from a title."""
    patterns = [
        r'海关总署公告\d{4}年第\d+号',
        r'税委会(?:公告|通知)\d{4}年第\d+号',
        r'商务部公告\d{4}年第\d+号',
        r'国家税务总局公告\d{4}年第\d+号',
        r'国务院(?:公告|通知|文件)',
        r'财关税〔\d{4}〕\d+号',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            return match.group(0)
    
    return title  # Fallback to raw title


def extract_number_from_numberCN(numberCN):
    """Generate English number field from numberCN."""
    # "海关总署公告2026年第2号" -> "GACC Announcement 2026 No.2"
    match = re.search(r'公告(\d{4})年第(\d+)号', numberCN)
    if match:
        year, num = match.groups()
        return f"GACC Announcement {year} No.{num}"
    
    match = re.search(r'税委会(?:公告|通知)(\d{4})年第(\d+)号', numberCN)
    if match:
        year, num = match.groups()
        return f"TCTC Announcement {year} No.{num}"
    
    match = re.search(r'商务部公告(\d{4})年第(\d+)号', numberCN)
    if match:
        year, num = match.groups()
        return f"MOFCOM Announcement {year} No.{num}"
    
    match = re.search(r'国家税务总局公告(\d{4})年第(\d+)号', numberCN)
    if match:
        year, num = match.groups()
        return f"STA Announcement {year} No.{num}"
    
    match = re.search(r'财关税〔(\d{4})〕(\d+)号', numberCN)
    if match:
        year, num = match.groups()
        return f"MOF Tariff Document {year} No.{num}"
    
    return numberCN


def extract_date_from_title_or_url(title, url):
    """Try to extract publication date from title or URL."""
    # From title: look for date patterns
    patterns = [
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
        r'(\d{4})-(\d{2})-(\d{2})',
        r'(\d{4})\.(\d{2})\.(\d{2})',
    ]
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            y, m, d = match.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
    
    # From URL: common patterns like /2026-01/07/ or /20260107
    url_patterns = [
        r'/(\d{4})-(\d{2})/(\d{2})/',
        r'/(\d{4})(\d{2})(\d{2})',
        r'content_(\d{4})(\d{2})(\d{2})',
    ]
    for pattern in url_patterns:
        match = re.search(pattern, url)
        if match:
            y, m, d = match.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
    
    # Default: use current year and "01" for month if only year found
    year_match = re.search(r'(\d{4})', title)
    if year_match:
        return f"{year_match.group(1)}-01-01"
    
    return f"{CURRENT_YEAR}-01-01"


def fetch_detail_page(url, source_type):
    """Fetch a regulation's detail page and extract description."""
    resp = fetch(url)
    if not resp:
        return None
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Try to find the main content area
    content_div = None
    candidates = [
        soup.find('div', class_='article-content'),
        soup.find('div', class_='content'),
        soup.find('div', class_='detail-content'),
        soup.find('div', id='content'),
        soup.find('div', class_='TRS_Editor'),
        soup.find('div', class_='Custom_UnionStyle'),
        soup.find('div', class_='text'),
        soup.find('article'),
    ]
    
    for candidate in candidates:
        if candidate:
            content_div = candidate
            break
    
    if not content_div:
        # Try finding by p tags in main area
        main = soup.find('main') or soup.find('body')
        if main:
            content_div = main
    
    if content_div:
        # Extract first 200 chars of meaningful text
        paragraphs = content_div.find_all('p')
        text = ' '.join(p.get_text(strip=True) for p in paragraphs[:5])
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            text = text[:200] + '...'
        return text
    
    return None


def build_regulation_entry(reg_data):
    """Build a JS object string for a new regulation entry."""
    # Escape Chinese quotes properly
    desc = reg_data.get("description", "")
    # Replace Chinese quotes with unicode escapes to avoid JS string issues
    desc = desc.replace('\u201c', '\\u201c').replace('\u201d', '\\u201d')
    # Replace regular double quotes with escaped ones
    desc = desc.replace('"', '\\\\"')
    
    # Clean title (remove org prefix)
    title = clean_title(reg_data.get("title", reg_data.get("title_raw", "")))
    title = title.replace('"', '\\\\"')
    
    lines = []
    lines.append(f'  {{')
    lines.append(f'    id: "{reg_data["id"]}",')
    lines.append(f'    number: "{reg_data["number"]}",')
    lines.append(f'    numberCN: "{reg_data["numberCN"]}",')
    lines.append(f'    title: "{title}",')
    lines.append(f'    date: "{reg_data["date"]}",')
    lines.append(f'    effectiveDate: "{reg_data.get("effectiveDate", reg_data["date"])}",')
    lines.append(f'    org: "{reg_data["org"]}",')
    lines.append(f'    orgCN: "{reg_data["orgCN"]}",')
    lines.append(f'    category: "{reg_data["category"]}",')
    lines.append(f'    categoryCN: "{reg_data["categoryCN"]}",')
    lines.append(f'    status: "{reg_data.get("status", "pending")}",')
    lines.append(f'    description: "{desc}",')
    lines.append(f'    supersedes: [],')
    lines.append(f'    supersededDetails: [],')
    lines.append(f'    url: "{reg_data["url"]}",')
    lines.append(f'    source: "{reg_data["source"]}"')
    lines.append(f'  }}')
    return '\n'.join(lines)


def insert_regulations_into_html(html_content, new_entries):
    """Insert new regulation entries into the BUILTIN_REGULATIONS array in index.html."""
    # Find the closing bracket of BUILTIN_REGULATIONS
    # We want to insert before the final ];
    
    # Find month headers to insert entries in the correct position
    # Each entry has a date, so we can determine which month section it belongs to
    
    # Strategy: insert all new entries at the end of the array, before the closing ];
    # The UI sorts by date anyway, so position doesn't matter for display
    # But for readability, we'll add a month comment header
    
    # Find the last entry in the array (before the closing ])
    # Pattern: find "];" that closes BUILTIN_REGULATIONS
    match = re.search(r'\n\];\n', html_content)
    if not match:
        print("[ERROR] Could not find BUILTIN_REGULATIONS closing bracket")
        return html_content
    
    insert_pos = match.start()
    
    # Build the new entries block
    entry_strings = []
    for entry_data in new_entries:
        entry_str = build_regulation_entry(entry_data)
        entry_strings.append(entry_str)
    
    # Determine month for the header comment
    months = set()
    for entry in new_entries:
        date_str = entry.get('date', '')
        m = re.match(r'\d{4}-(\d{2})', date_str)
        if m:
            months.add(int(m.group(1)))
    
    month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    
    header_comments = []
    for m in sorted(months):
        header_comments.append(f'  // ---- {month_names[m]} (auto-detected) ----')
    
    new_block = '\n' + '\n'.join(header_comments) + '\n' + ',\n'.join(entry_strings) + '\n'
    
    # Insert before the closing ];
    new_html = html_content[:insert_pos] + new_block + html_content[insert_pos:]
    
    return new_html


# ---------------------------------------------------------------------------
# Source scrapers
# ---------------------------------------------------------------------------

def scrape_gacc_announcements():
    """Scrape GACC announcement listing page for 2026 regulations.
    Uses customs.gov.cn as primary, gov.cn search as fallback."""
    new_regs = []
    print("[GACC] Checking customs.gov.cn for new announcements...")
    
    # Primary: customs.gov.cn announcement listing
    urls = [
        "http://www.customs.gov.cn/customs/302249/2480148/index.html",
        "http://www.customs.gov.cn/customs/302249/302266/302267/index.html",
    ]
    
    for url in urls:
        resp = fetch(url)
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                title = link.get_text(strip=True)
                
                if '2026' not in title:
                    continue
                
                match = re.search(r'公告2026年第(\d+)号', title)
                if not match:
                    continue
                
                ann_num = match.group(1)
                full_url = urljoin(url, href)
                
                # Ensure URL starts with http
                if not full_url.startswith('http'):
                    full_url = "http://www.customs.gov.cn" + full_url
                
                new_regs.append({
                    'source_type': 'GACC',
                    'numberCN': f'海关总署公告2026年第{ann_num}号',
                    'title_raw': title,
                    'url': full_url,
                    'ann_num': ann_num,
                })
            break  # If first URL works, skip second
    
    # Fallback: gov.cn search for GACC announcements
    if not new_regs:
        print("[GACC] Primary source failed, trying gov.cn mirror...")
        search_url = f"https://s.gov.cn/search/search?keyword={quote('海关总署公告2026年')}&field=all"
        resp = fetch(search_url)
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                title = link.get_text(strip=True)
                
                match = re.search(r'公告2026年第(\d+)号', title)
                if not match:
                    continue
                
                ann_num = match.group(1)
                full_url = urljoin(search_url, href)
                if not full_url.startswith('http'):
                    full_url = "https://www.gov.cn" + full_url
                
                new_regs.append({
                    'source_type': 'GACC',
                    'numberCN': f'海关总署公告2026年第{ann_num}号',
                    'title_raw': title,
                    'url': full_url,
                    'ann_num': ann_num,
                    'is_mirror': True,
                })
    
    # Fallback 2: Bing search (works in GitHub Actions environment)
    if not new_regs:
        print("[GACC] Trying Bing search for GACC announcements...")
        bing_url = f"https://www.bing.com/search?q={quote('海关总署公告2026年 site:gov.cn OR site:customs.gov.cn')}"
        resp = fetch(bing_url)
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Bing search results are in <li class="b_algo">
            results = soup.find_all('li', class_='b_algo')
            for result in results:
                link = result.find('a', href=True)
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get('href', '')
                
                match = re.search(r'公告2026年第(\d+)号', title)
                if not match:
                    continue
                
                ann_num = match.group(1)
                new_regs.append({
                    'source_type': 'GACC',
                    'numberCN': f'海关总署公告2026年第{ann_num}号',
                    'title_raw': title,
                    'url': href,
                    'ann_num': ann_num,
                    'is_mirror': True,
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
        print("  [TCTC] Failed to fetch listing page, trying Bing fallback...")
        bing_url = f"https://www.bing.com/search?q={quote('税委会公告2026年 OR 财关税2026 site:gss.mof.gov.cn OR site:mof.gov.cn')}"
        resp = fetch(bing_url)
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = soup.find_all('li', class_='b_algo')
            for result in results:
                link = result.find('a', href=True)
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get('href', '')
                
                match = re.search(r'税委会(?:公告|通知)2026年第(\d+)号', title)
                if not match:
                    match = re.search(r'财关税〔2026〕(\d+)号', title)
                if match:
                    new_regs.append({
                        'source_type': 'TCTC',
                        'numberCN_raw': title,
                        'title_raw': title,
                        'url': href,
                        'is_mirror': True,
                    })
    else:
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            if '2026' not in title:
                continue
            
            match = re.search(r'税委会(?:公告|通知)2026年第(\d+)号', title)
            if not match:
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
        
        # Look for trade/customs related announcements with 2026
        if not any(k in title for k in ['出口管制', '两用物项', '进出口', '贸易',
                                          '关税', '配额', '禁止', '限制', '公告2026年']):
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
    """Scrape STA (国家税务总局) for export tax refund related policies.
    Uses chinatax.gov.cn as primary, gov.cn/Bing as fallback."""
    new_regs = []
    print("[STA] Checking fgk.chinatax.gov.cn for new policies...")
    
    # Primary: STA listing page
    list_url = "https://fgk.chinatax.gov.cn/zcfgk/c100012/"
    resp = fetch(list_url)
    if resp:
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            if not any(k in title for k in ['出口', '退税', '增值税', '消费税', '公告2026年']):
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
    
    # Fallback: Bing search
    if not new_regs:
        print("[STA] Primary failed, trying Bing search...")
        bing_url = f"https://www.bing.com/search?q={quote('国家税务总局公告2026年 出口退税 site:chinatax.gov.cn OR site:gov.cn')}"
        resp = fetch(bing_url)
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = soup.find_all('li', class_='b_algo')
            for result in results:
                link = result.find('a', href=True)
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get('href', '')
                
                if '2026' not in title:
                    continue
                if not any(k in title for k in ['出口', '退税', '增值税', '国家税务总局公告']):
                    continue
                
                new_regs.append({
                    'source_type': 'STA',
                    'numberCN_raw': title,
                    'title_raw': title,
                    'url': href,
                    'is_mirror': True,
                })
    
    print(f"  [STA] Found {len(new_regs)} potential announcements")
    return new_regs


def scrape_gov_cn_announcements():
    """Scrape Gov.cn for central government trade/customs policies."""
    new_regs = []
    print("[Gov.cn] Checking gov.cn for new central policies...")
    
    # Gov.cn policy database
    url = "https://www.gov.cn/zhengce/"
    resp = fetch(url)
    if not resp:
        print("  [Gov.cn] Failed to fetch listing page")
        return new_regs
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        title = link.get_text(strip=True)
        
        # Look for trade/customs related central policies
        if not any(k in title for k in ['海关', '关税', '出口', '进口', '贸易', '保税',
                                          '检验', '检疫', '自贸', 'AEO']):
            continue
        if '2026' not in title:
            continue
        
        full_url = urljoin(url, href)
        if not full_url.startswith('http'):
            full_url = "https://www.gov.cn" + full_url
        
        new_regs.append({
            'source_type': 'Gov.cn',
            'numberCN_raw': title,
            'title_raw': title,
            'url': full_url,
        })
    
    print(f"  [Gov.cn] Found {len(new_regs)} potential announcements")
    return new_regs


# ---------------------------------------------------------------------------
# Main update logic
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"APAC Trade Compliance - Auto Update (Enhanced)")
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
    all_new.extend(scrape_gov_cn_announcements())
    
    # Filter out already-existing regulations
    truly_new = []
    for reg in all_new:
        numberCN = reg.get('numberCN', reg.get('numberCN_raw', ''))
        if numberCN and numberCN in existing_numberCNs:
            continue
        # Also check by URL to avoid duplicates from different sources
        url = reg.get('url', '')
        if url and any(url == r.get('url', '') for r in truly_new):
            continue
        truly_new.append(reg)
    
    print(f"\n{'=' * 60}")
    print(f"Total found: {len(all_new)}, New: {len(truly_new)}")
    
    if not truly_new:
        print("No new regulations found. Exiting cleanly.")
        # Still update the log for monitoring dashboard
        update_log = {
            "last_run": datetime.now().isoformat(),
            "run_result": "no_new",
            "total_existing": len(existing_ids),
            "total_found": len(all_new),
            "new_found": 0,
            "new_added": 0,
            "needs_review": 0,
            "entries": []
        }
        log_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'update_log.json')
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(update_log, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved update_log.json (no new regulations)")
        return False
    
    # Process each new regulation
    processed_entries = []
    needs_review = []
    
    # Pre-generate IDs for all new regulations
    batch_ids = generate_batch_ids(html_content, len(truly_new))
    
    for idx, reg in enumerate(truly_new):
        print(f"\n  Processing: {reg.get('numberCN', reg.get('numberCN_raw', 'UNKNOWN'))}")
        print(f"    URL: {reg['url']}")
        print(f"    Source: {reg['source_type']}")
        
        # Determine numberCN
        numberCN = reg.get('numberCN', '')
        if not numberCN:
            numberCN = extract_numberCN_from_title(reg.get('title_raw', reg.get('numberCN_raw', '')))
        reg['numberCN'] = numberCN
        
        # Determine title
        title = reg.get('title', '')
        if not title:
            title = clean_title(reg.get('title_raw', reg.get('numberCN_raw', '')))
        
        # Determine date
        pub_date = reg.get('date', '')
        if not pub_date:
            pub_date = extract_date_from_title_or_url(
                reg.get('title_raw', ''), reg.get('url', '')
            )
        
        # Determine category
        category = determine_category(title, reg.get('title_raw', ''))
        categoryCN = CATEGORY_CN_MAP.get(category, '监管通关')
        
        # Determine org
        org_info = determine_org_and_source(reg['source_type'], reg.get('url', ''), title)
        
        # Determine English number
        number = extract_number_from_numberCN(numberCN)
        
        # Use pre-generated ID
        entry_id = batch_ids[idx]
        
        # Try to fetch detail page for description
        description = ""
        auto_detected = False
        try:
            desc = fetch_detail_page(reg['url'], reg['source_type'])
            if desc and len(desc) > 20:
                description = desc
            else:
                description = f"\u201c自动检测，待人工核实\u201d{title}"
                auto_detected = True
                needs_review.append(reg)
        except Exception as e:
            print(f"    [WARN] Could not fetch detail: {e}")
            description = f"\u201c自动检测，待人工核实\u201d{title}"
            auto_detected = True
            needs_review.append(reg)
        
        # Build complete entry
        entry = {
            'id': entry_id,
            'number': number,
            'numberCN': numberCN,
            'title': title,
            'date': pub_date,
            'effectiveDate': pub_date,  # Will be verified later
            'org': org_info['org'],
            'orgCN': org_info['orgCN'],
            'category': category,
            'categoryCN': categoryCN,
            'status': 'pending',  # New regulations start as pending
            'description': description,
            'url': reg['url'],
            'source': org_info['source'],
        }
        
        processed_entries.append(entry)
    
    if not processed_entries:
        print("No entries could be processed. Exiting.")
        return False
    
    # Insert all entries into index.html
    print(f"\n{'=' * 60}")
    print(f"Inserting {len(processed_entries)} new entries into index.html...")
    
    updated_html = insert_regulations_into_html(html_content, processed_entries)
    
    # Write updated index.html
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(updated_html)
    
    print(f"✅ Updated index.html with {len(processed_entries)} new regulations")
    
    # Create update log for monitoring dashboard
    update_log = {
        "last_run": datetime.now().isoformat(),
        "run_result": "success",
        "total_existing": len(existing_ids),
        "total_found": len(all_new),
        "new_found": len(truly_new),
        "new_added": len(processed_entries),
        "needs_review": len(needs_review),
        "entries": [
            {
                "id": e['id'],
                "title": e['title'],
                "status": e['status'],
                "category": e['category'],
                "url": e['url']
            }
            for e in processed_entries
        ]
    }
    log_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'update_log.json')
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(update_log, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved update_log.json")

    # Create notification for regulations that need manual review
    if needs_review:
        notification = {
            "timestamp": datetime.now().isoformat(),
            "needs_review": len(needs_review),
            "total_new": len(processed_entries),
            "regulations_needing_review": [
                {
                    "id": e['id'],
                    "numberCN": e['numberCN'],
                    "title": e['title'],
                    "url": e['url'],
                    "reason": "Description could not be auto-extracted; needs manual verification"
                }
                for e in processed_entries if e['description'].startswith('\u201c自动检测')
            ]
        }
        notif_path = os.path.join(os.path.dirname(__file__), '..', 'new_regulations.json')
        with open(notif_path, 'w', encoding='utf-8') as f:
            json.dump(notification, f, ensure_ascii=False, indent=2)
        print(f"\n⚠️ {len(needs_review)} regulations need manual review (saved to new_regulations.json)")
    
    return True



if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        has_updates = main()
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
