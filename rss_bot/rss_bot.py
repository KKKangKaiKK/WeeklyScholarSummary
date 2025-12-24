import requests
import json
import os
import re
import time
from datetime import datetime, timedelta,date
from concurrent.futures import ThreadPoolExecutor
import feedparser
from bs4 import BeautifulSoup
import html



# --- 新增：抑制针对特定连接的 InsecureRequestWarning ---
# 我们将在代码中精确控制 SSL 验证，因此可以安全地禁用此警告
import urllib3
from urllib3.exceptions import InsecureRequestWarning
urllib3.disable_warnings(InsecureRequestWarning)
# ----------------------------------------------------

# --- 1. 配置与缓存管理 ---

def load_config(filename="config.json"):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：配置文件 '{filename}' 未找到。请根据模板创建。")
        exit()

def save_cache(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"进度已保存到: {filename}")

def load_cache(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            print(f"从缓存加载: {filename}")
            return json.load(f)
    return None

# --- 2. 基于 Requests 的 LLM 客户端 ---

def requests_based_llm_call(client_config, prompt):
    """
    使用 requests 库调用 API，支持超时自动重试。
    """
    api_base = client_config['api_base']
    api_key = client_config['api_key']
    model = client_config['model']
    verify_ssl = client_config.get('verify_ssl', True)
    
    # 获取最大重试次数，默认为 3 次 (即如果超时，会额外尝试 2 次)
    max_retries = client_config.get('max_retries', 3)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }

    # 开始循环尝试
    for attempt in range(1, max_retries + 1):
        try:
            # 打印调试信息 (可选)
            # if attempt > 1:
            #     print(f"正在进行第 {attempt} 次尝试...")

            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                verify=verify_ssl,
                timeout=240 # 设置超时时间
            )
            response.raise_for_status()
            
            # --- 解析成功，处理数据 ---
            data = response.json()
            content = data['choices'][0]['message']['content']
            cleaned_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            return cleaned_content.strip()

        except requests.exceptions.Timeout as e:
            # 专门捕获超时错误 (Read timed out / Connect timed out)
            print(f"[{client_config['name']}] 第 {attempt} 次请求超时: {e}")
            
            if attempt < max_retries:
                wait_time = 2  # 重试前等待 2 秒
                print(f"将在 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue  # 进入下一次循环
            else:
                print(f"[{client_config['name']}] 已达到最大重试次数，放弃。")
                return None

        except requests.exceptions.RequestException as e:
            # 捕获其他网络错误 (如 404, 500, DNS 错误等)，通常这些不需要立即重试或需单独处理
            print(f"与 LLM 服务器 ({client_config['name']}) 通信时发生非超时网络错误: {e}")
            return None
            
        except (KeyError, IndexError) as e:
            # 解析错误，说明连接成功但返回格式不对，不需要重试
            print(f"解析 LLM 服务器 ({client_config['name']}) 的响应时出错: {e}")
            # 为了调试，可以打印 response.text，但在发生异常时 response 可能未定义，需小心
            return None

    return None
# --- 3. RSS 拉取与内容处理 ---

def get_article_full_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        # 修改：移除 verify=False，恢复对外部网站的证书验证
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        article_body = soup.find('article') or soup.find('div', class_='post-content') or soup.find('div', class_='content')
        if article_body:
            return article_body.get_text(separator='\n', strip=True)
        return None
    except Exception:
        return None

def fetch_and_filter_rss(feed_urls, days_to_scan, existing_links):
    scan_since_date = datetime.now() - timedelta(days=days_to_scan)
    new_articles = []

    for url in feed_urls:
        print(f"正在处理 RSS源: {url}")
        feed = feedparser.parse(url)
        for entry in feed.entries:
            published_time = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_time = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            
            if published_time and published_time >= scan_since_date:
                if entry.link in existing_links:
                    continue

                content = entry.get('summary', '')
                full_content = get_article_full_content(entry.link)
                if full_content:
                    content = full_content

                new_articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "content": content,
                    "published": published_time.strftime("%Y-%m-%d"),
                    "category": None
                })
    return new_articles

# --- 4. LLM 核心逻辑 (分类与总结) ---

def classify_article_worker(article_with_index, client_config, topics):
    index, article = article_with_index
    print(f"  [线程: {client_config['name']}] 正在分类: {article['title'][:30]}...")
    
    prompt = f"""
    请判断以下文章内容主要与哪个话题最相关。话题列表：{topics}。
    分类原则（非常重要）：
    1. **优先特异性**：如果文章内容同时符合“话题A”和“话题A的子领域B”，必须返回 **“话题B”**。
    2. **拒绝宽泛**：只有在文章内容完全无法匹配任何更具体的子话题时，才允许返回较宽泛的父级话题。
    3. **精准匹配**：请返回话题列表中最狭窄、定义最具体的那个概念。
    4. 如果内容与任何一个话题都不太相关，请返回 "其他"。

    如果你支持推理，请简短思考该文章是否属于某个话题的细分领域；如果不支持，请直接输出结果。
    请只返回最相关的话题名称，**不要**添加任何解释、标点符号或前缀后缀。

    文章内容：
    ---
    {article['title']}
    {article['content'][:500]}
    ---
    最相关的话题是：
    """
    category = requests_based_llm_call(client_config, prompt)
    print(f"  {article['title'][:40]}...，分类结果：{category}")
    return index, category


def summarize_articles(client_config, articles_content):
    # --- MODIFICATION START (Request 3: AI instruction) ---
    # 添加了明确指令，要求AI不要使用Markdown加粗
    prompt = f"""
    请根据以下文章内容，为这个主题生成一个丰富、有条理的周报总结。没有篇幅限制，总结越长越好。
    请直接开始写总结，不要有引言。
    重要：在你的回答中，请不要使用 Markdown 的加粗语法（例如 **文字**），直接生成纯文本即可。

    文章内容：
    ---
    {articles_content}
    ---
    本周总结：
    """
    # --- MODIFICATION END ---
    return requests_based_llm_call(client_config, prompt)


# --- 5. HTML 生成 (内联 CSS) ---

# --- MODIFICATION START (Request 1, 2, 3: HTML generation) ---
# 全面重构此函数以实现新的设计、处理空话题并添加历史链接
def generate_html_inline_css(categorized_articles, summaries, filename):
    report_date = datetime.now().strftime('%Y-%m-%d')
    
    # 更现代化的样式设计
    styles = {
        'body': 'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "PingFang SC", "Microsoft YaHei", sans-serif; line-height: 1.7; color: #4a4a4a; background-color: #f4f7f9; margin: 0; padding: 15px;',
        'container': 'max-width: 800px; margin: 20px auto; background-color: #ffffff; padding: 30px 40px; border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.07);',
        'header': 'text-align: center; border-bottom: 1px solid #e0e0e0; padding-bottom: 20px; margin-bottom: 35px;',
        'h1': 'margin: 0; color: #2c3e50; font-size: 28px; font-weight: 700;',
        'date': 'color: #888; font-size: 15px; margin-top: 8px;',
        'history_link_p': 'margin-top: 15px;',
        'history_link_a': 'color: #3498db; text-decoration: none; font-size: 14px; transition: color 0.3s;',
        'category_section': 'margin-bottom: 40px;',
        'h2': 'color: #2980b9; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-top: 0; font-size: 24px; font-weight: 600;',
        'summary_box': 'background-color: #f8f9fa; padding: 20px 25px; border-radius: 8px; margin-bottom: 28px; border-left: 4px solid #3498db;',
        'h3': 'margin-top: 0; margin-bottom: 12px; color: #34495e; font-size: 18px; font-weight: 600;',
        'p': 'margin: 0; line-height: 1.8;',
        'h4': 'margin-top: 0; margin-bottom: 18px; font-size: 17px; color: #34495e; font-weight: 600;',
        'ul': 'list-style-type: none; padding: 0; margin: 0;',
        'li': 'margin-bottom: 16px; padding-left: 22px; position: relative;',
        'li_before': 'content: "▪"; color: #3498db; position: absolute; left: 0; top: 1px; font-size: 18px;',
        'a': 'text-decoration: none; color: #2c3e50; font-weight: 500; font-size: 16px; transition: color 0.3s;',
        'meta': 'color: #7f8c8d; font-size: 13px; margin-left: 10px;',
        'footer': 'text-align: center; margin-top: 40px; padding-top: 25px; border-top: 1px solid #e0e0e0; color: #b0b0b0; font-size: 13px;',
        'no_articles_box': 'background-color: #fcfcfc; color: #999; padding: 20px 25px; border-radius: 8px; border: 1px dashed #ddd; text-align: center; font-style: italic;'
    }
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>每周RSS动态总结 - {report_date}</title>
        <style>
            a:hover {{ color: #e74c3c !important; }}
        </style>
    </head>
    <body style="{styles['body']}">
        <div style="{styles['container']}">
            <div style="{styles['header']}">
                <h1 style="{styles['h1']}">每周 RSS 动态总结</h1>
                <p style="{styles['date']}">{report_date}</p>
                {'''<!-- Request 1: 添加回顾历史汇总链接 -->'''}
                <p style="{styles['history_link_p']}">
                    <a href="https://github.com/KKKangKaiKK/WeeklyScholarSummary/tree/main/summaries" target="_blank" rel="noopener noreferrer" style="{styles['history_link_a']}">🔗 回顾历史汇总</a>
                </p>
            </div>
    """
    
    # 检查是否有任何文章被分类
    if not categorized_articles:
        html_content += f"<div style='{styles['no_articles_box']}'><p>本周扫描范围内，没有发现与您配置的任何话题相关的新文章。</p></div>"
    else:
        # Request 2: 循环遍历所有感兴趣的话题，而不仅仅是有总结的话题
        for category, articles in categorized_articles.items():
            safe_category = html.escape(category)
            
            html_content += f"""
            <div style="{styles['category_section']}">
                <h2 style="{styles['h2']}">{safe_category}</h2>
            """
            
            # 如果这个分类下有文章
            if articles:
                summary = summaries.get(category) # 从summaries字典获取总结
                if summary:
                    formatted_summary = html.escape(summary).replace('\n', '<br>')
                    html_content += f"""
                    <div style="{styles['summary_box']}">
                        <h3 style="{styles['h3']}">本周观察</h3>
                        <p style="{styles['p']}">{formatted_summary}</p>
                    </div>
                    """
                
                html_content += f"""
                <div>
                    <h4 style="{styles['h4']}">相关文章列表</h4>
                    <ul style="{styles['ul']}">
                """
                
                for article in articles:
                    safe_title = html.escape(article['title'])
                    safe_link = html.escape(article['link'])
                    safe_published = html.escape(article['published'])
                    # 使用 <li> 伪元素 :before 来创建项目符号
                    html_content += f"""
                        <li style="{styles['li']}">
                            <span style='{styles['li_before']}'></span>
                            <a href="{safe_link}" target="_blank" rel="noopener noreferrer" style="{styles['a']}">{safe_title}</a>
                            <span style="{styles['meta']}">({safe_published})</span>
                        </li>
                    """
                html_content += "</ul></div>"
            
            # 如果这个分类下没有文章
            else:
                html_content += f"""
                <div style="{styles['no_articles_box']}">
                    <p>本周未发现关于 “{safe_category}” 话题的新文章。</p>
                </div>
                """
            
            html_content += "</div>"

    html_content += f"""
            <div style="{styles['footer']}">
                <p>由 RSS Summary Bot 自动生成</p>
            </div>
        </div>
    </body>
    </html>
    """

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML 报告已生成: {filename}")
# --- MODIFICATION END ---


# --- 6. 主逻辑 ---

def main():
    config = load_config()
    prefix = config['cache_filename_prefix']
    
    last_week_file = f"{prefix}_last_week.json"
    fetched_file = f"{prefix}_fetched.json"
    classified_file = f"{prefix}_classified.json"

    last_week_data = load_cache(last_week_file)
    if last_week_data:
        days_to_scan = 8
        existing_links = {article['link'] for article in last_week_data}
        print(f"检测到上周记录，将扫描过去 {days_to_scan} 天的内容，并排除 {len(existing_links)} 个旧链接。")
    else:
        days_to_scan = 15
        existing_links = set()
        print(f"未检测到上周记录，将进行首次扫描，范围为过去 {days_to_scan} 天。")

    articles_to_process = load_cache(fetched_file)
    if not articles_to_process:
        print("\n--- 开始获取新文章 ---")
        articles_to_process = fetch_and_filter_rss(config['rss_feeds'], days_to_scan, existing_links)
        print(f"获取到 {len(articles_to_process)} 篇新文章。")
        save_cache(articles_to_process, fetched_file)
    else:
        print(f"从缓存加载了 {len(articles_to_process)} 篇待处理文章。")


    classified_articles = load_cache(classified_file)
    if not classified_articles:
        print("\n--- 开始并行分类文章 ---")
        clients = config['llm_clients'][1:]
        num_clients = len(clients)
        tasks = [( (i, article), clients[i % num_clients], config['interesting_topics'] ) for i, article in enumerate(articles_to_process)]
        
        with ThreadPoolExecutor(max_workers=num_clients) as executor:
            results = executor.map(lambda p: classify_article_worker(*p), tasks)

        for index, category in results:
            if category and category != "其他":
                articles_to_process[index]['category'] = category
        
        classified_articles = [a for a in articles_to_process if a['category']]
        print(f"分类完成，共有 {len(classified_articles)} 篇相关文章。")
        save_cache(classified_articles, classified_file)
    else:
         print(f"从缓存加载了 {len(classified_articles)} 篇已分类文章。")

    print("\n--- 开始生成总结 ---")
    categorized_articles = {}
    for topic in config['interesting_topics']:
        categorized_articles[topic] = [a for a in classified_articles if a['category'] == topic]

    summaries = {}
    summarizer_client = config['llm_clients'][0]
    for category, articles in categorized_articles.items():
        if not articles:
            continue
        print(f"正在总结类别: {category} ({len(articles)}篇文章)")
        combined_content = "\n\n---\n\n".join(
            [f"标题: {a['title']}\n内容摘要: {a['content'][:1000]}" for a in articles]
        )
        summary = summarize_articles(summarizer_client, combined_content)
        if summary:
            summaries[category] = summary

    print("\n--- 开始生成 HTML 报告 ---")

    today = date.today()
    formatted_date = today.strftime("%Y-%m-%d")
    generate_html_inline_css(categorized_articles, summaries, f"{formatted_date}.html")

    print("\n--- 清理缓存并更新状态 ---")
    if os.path.exists(last_week_file):
        os.remove(last_week_file)
        print(f"已删除旧的状态文件: {last_week_file}")
    
    if os.path.exists(classified_file):
        os.rename(classified_file, last_week_file)
        print(f"当前分类结果已存为下一周的记录: {last_week_file}")

    if os.path.exists(fetched_file):
        os.remove(fetched_file)
        print(f"已删除本次的中间缓存: {fetched_file}")

    print("\n任务全部完成！")


if __name__ == "__main__":
    main()
