from ruijie_integration import get_token
import requests,json
t=get_token()
print("Token:",t[:15])
base="https://cloud.ruijienetworks.com"
r1=requests.get(f"{base}/service/api/maint/devices?common_type=AP&group_id=9104528&page=1&per_page=50&access_token={t}",timeout=15)
print("AP:",json.dumps(r1.json(),indent=2)[:500])
