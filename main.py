import os,json,time,logging,anthropic,requests
from dotenv import load_dotenv
load_dotenv()
BANKROLL=100.00
MAX_BET_PCT=0.05
MAX_POSITIONS=4
MIN_EDGE=0.05
MIN_LIQUIDITY=5000
FOCUS=["bitcoin","btc","eth","crypto","nba","nfl","mlb","gdp","fed","inflation","recession","rate","cpi","unemployment","nasdaq","sports","championship"]
GAMMA_URL="https://gamma-api.polymarket.com"
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(levelname)s] %(message)s")
log=logging.getLogger("polybot")
def get_client():
    from polymarket_us import PolymarketUS
    key_id=os.getenv("API_KEY_ID","").strip()
    private_key=os.getenv("PRIVATE_KEY","").strip()
    if not key_id or not private_key:
        raise ValueError("API_KEY_ID or PRIVATE_KEY missing")
    return PolymarketUS(api_key_id=key_id,private_key=private_key)
def fetch_markets():
    try:
        r=requests.get(f"{GAMMA_URL}/markets",params={"active":True,"closed":False,"limit":100},timeout=10)
        r.raise_for_status()
        markets=r.json()
    except Exception as e:
        log.error(f"Market fetch failed: {e}");return []
    filtered=[m for m in markets if float(m.get("volume") or 0)>=MIN_LIQUIDITY and any(k in (m.get("question") or "").lower() for k in FOCUS)]
    log.info(f"{len(filtered)} markets found")
    return filtered[:20]
def ai_analyze(markets):
    client=anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    summaries=[{"id":m.get("id"),"question":m.get("question"),"yes_price":m.get("bestAsk") or m.get("lastTradePrice"),"volume":m.get("volume")} for m in markets]
    prompt="You are an expert prediction market trader managing $100 on Polymarket.\nFocus: Crypto, Sports, Economics.\nOnly recommend BUY when edge is greater than 5 cents.\nMarkets:\n"+json.dumps(summaries,indent=2)+"\nReply ONLY with a JSON array, no markdown:\n[{\"market_id\":\"...\",\"question\":\"...\",\"action\":\"BUY or SKIP\",\"side\":\"YES or NO\",\"true_prob\":0.00,\"market_price\":0.00,\"edge\":0.00,\"confidence\":\"HIGH or MEDIUM or LOW\",\"reasoning\":\"one sentence\"}]"
    resp=client.messages.create(model="claude-sonnet-4-20250514",max_tokens=2000,messages=[{"role":"user","content":prompt}])
    raw=resp.content[0].text.strip().replace("```json","").replace("```","")
    try:
        decisions=json.loads(raw)
        buys=[d for d in decisions if d.get("action")=="BUY" and d.get("edge",0)>=MIN_EDGE]
        log.info(f"AI found {len(buys)} BUY signals")
        return decisions
    except Exception as e:
        log.error(f"Parse error: {e}");return []
def place_trade(client,decision,open_count):
    if open_count>=MAX_POSITIONS:return False
    if decision.get("confidence")=="LOW":return False
    price=float(decision.get("market_price",0))
    if price<=0 or price>=1:return False
    bet=round(BANKROLL*MAX_BET_PCT,2);shares=round(bet/price,1)
    log.info(f"ORDER: {decision['side']} {shares} shares @ {price:.2f}")
    try:
        resp=client.place_order(market_id=decision["market_id"],side=decision["side"],price=price,size=shares)
        log.info(f"Filled: {resp}");return True
    except Exception as e:
        log.error(f"Order failed: {e}");return False
def run():
    log.info("Polymarket AI Bot -- Starting")
    try:client=get_client()
    except Exception as e:log.error(f"Startup failed: {e}");return
    cycle=0
    while True:
        cycle+=1;log.info(f"Cycle {cycle}")
        markets=fetch_markets()
        if not markets:time.sleep(300);continue
        decisions=ai_analyze(markets)
        buys=[d for d in decisions if d.get("action")=="BUY" and d.get("edge",0)>=MIN_EDGE]
        placed=0
        for d in buys[:2]:
            if place_trade(client,d,placed):placed+=1;time.sleep(2)
        log.info(f"Cycle {cycle} done. {placed} trades. Sleeping 15 min...")
        time.sleep(900)
if __name__=="__main__":run()
