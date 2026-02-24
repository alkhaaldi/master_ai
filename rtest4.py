from ruijie_integration import get_token
import requests,json
t=get_token()
b="https://cloud.ruijienetworks.com"
r=requests.get(f"{b}/service/api/maint/groups?access_token={t}",timeout=15)
print(json.dumps(r.json(),ensure_ascii=False,indent=2)[:2000])
