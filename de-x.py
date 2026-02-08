##
# de-x.py -- delete all your tweets w/o API access
# Copyright 2023 Thorsten Schroeder
#
# Published under 2-Clause BSD License (https://opensource.org/license/bsd-2-clause/)
#
# Please see README.md for more information
##

import sys
import json
import requests
import time
import os

def get_tweet_ids(json_data):

    result = []
    data = json.loads(json_data)

    for d in data:
        result.append(d['tweet']['id_str'])

    return result

def load_deleted_tweets(deleted_file):
    if not os.path.exists(deleted_file):
        return set()
    
    with open(deleted_file, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def save_deleted_tweet(deleted_file, tweet_id):
    with open(deleted_file, 'a') as f:
        f.write(f"{tweet_id}\n")

def parse_req_headers(request_file):

    sess = {}
    
    with open(request_file) as f:
        content = f.read()
    
    # Try to parse as fetch format (JSON with headers object)
    if '"headers"' in content or "'headers'" in content:
        try:
            # Extract the fetch call object
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                fetch_obj = json.loads(content[start:end])
                if 'headers' in fetch_obj:
                    for k, v in fetch_obj['headers'].items():
                        # Normalize header names to Title-Case
                        k = '-'.join(word.capitalize() for word in k.split('-'))
                        sess[k] = v
                    return sess
        except:
            pass
    
    # Fallback to simple key: value format
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            k, v = line.split(':', 1)
            val = v.lstrip().rstrip()
            # Normalize header names to Title-Case
            k = '-'.join(word.capitalize() for word in k.strip().split('-'))
            sess[k] = val
        except:
            pass

    return sess

def main(ac, av):

    if(ac != 3):
        print(f"[!] usage: {av[0]} <jsonfile> <req-headers>")
        return

    f = open(av[1], encoding='UTF-8')
    raw = f.read()
    f.close()

    # skip data until first '['
    i = raw.find('[')
    ids = get_tweet_ids(raw[i:])

    session = parse_req_headers(av[2])

    deleted_file = 'deleted_tweets.txt'
    deleted_tweets = load_deleted_tweets(deleted_file)
    
    ids_to_delete = [tid for tid in ids if tid not in deleted_tweets]
    
    if len(deleted_tweets) > 0:
        print(f"[+] Loaded {len(deleted_tweets)} already-deleted tweets")
        print(f"[+] Skipping {len(ids) - len(ids_to_delete)} tweets")
    
    total = len(ids_to_delete)
    if total == 0:
        print("[+] All tweets already deleted!")
        return
    
    print(f"[+] {total} tweets remaining to delete\n")
    
    for idx, i in enumerate(ids_to_delete, 1):
        success = delete_tweet(session, i, idx, total)
        if success:
            save_deleted_tweet(deleted_file, i)
        # small delay between requests, will auto-wait on 429
        if idx < total:
            time.sleep(2)


def delete_tweet(session, tweet_id, index, total):

    print(f"[*] [{index}/{total}] delete tweet-id {tweet_id}")
    delete_url = "https://x.com/i/api/graphql/VaenaVgh5q5ih7kvyVjgtg/DeleteTweet"
    data = {"variables":{"tweet_id":tweet_id,"dark_request":False},"queryId":"VaenaVgh5q5ih7kvyVjgtg"}

    # set or re-set correct content-type header
    session["Content-Type"] = 'application/json'
    
    # Ensure critical headers are present
    if "User-Agent" not in session:
        session["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    if "Origin" not in session:
        session["Origin"] = "https://x.com"
    if "Referer" not in session:
        session["Referer"] = "https://x.com/home"
    
    print(f"[*] API endpoint: {delete_url}")
    print(f"[*] Request data: {json.dumps(data)}")
    print(f"[*] Has Cookie header: {'Cookie' in session}")
    print(f"[*] Headers sent: {list(session.keys())}")
    
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            r = requests.post(delete_url, data=json.dumps(data), headers=session, timeout=30)
            print(f"[*] Response status: {r.status_code} {r.reason}")
            print(f"[*] Response headers: {dict(r.headers)}")
            
            rate_limit = r.headers.get('x-rate-limit-limit')
            rate_remaining = r.headers.get('x-rate-limit-remaining')
            rate_reset = r.headers.get('x-rate-limit-reset')
            
            if rate_limit and rate_remaining:
                print(f"[i] Rate limit: {rate_remaining}/{rate_limit} remaining")
            
            if r.status_code == 429:
                if rate_reset:
                    reset_time = int(rate_reset)
                    current_time = int(time.time())
                    wait_time = max(reset_time - current_time + 5, 60)
                    print(f"[!] Rate limit exceeded. Waiting {wait_time}s until reset (at {time.strftime('%H:%M:%S', time.localtime(reset_time))})")
                else:
                    wait_time = 60 * (2 ** attempt)
                    print(f"[!] Rate limit hit. Waiting {wait_time}s before retry... (attempt {attempt + 1}/{max_retries})")
                
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[!] Rate limit persists after {max_retries} attempts.")
                    print(f"[!] Stopping execution. Run script again later to continue.")
                    sys.exit(1)
            
            print(r.text[:500] + '...')
            
            if r.status_code == 200:
                if rate_remaining and int(rate_remaining) < 5:
                    print(f"[!] Low rate limit remaining ({rate_remaining}). Adding extra 5s delay...")
                    time.sleep(5)
                return True
            else:
                print(f"[!] Unexpected status code {r.status_code}. Response body: {r.text[:1000]}")
                if r.status_code == 403:
                    print(f"[!] 403 Forbidden - Check if headers (especially authorization tokens) are still valid")
                return False
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                print(f"[!] Connection error: {type(e).__name__}. Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print(f"[!] Failed after {max_retries} attempts. Error: {type(e).__name__}")
                print(f"[!] Skipping tweet-id {tweet_id} and continuing...")
                return False
    
    return False


if __name__ == '__main__':

    main(len(sys.argv), sys.argv)
