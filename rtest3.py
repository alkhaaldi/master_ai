from ruijie_integration import get_token
import requests,json
t=get_token()
b="https://cloud.ruijienetworks.com"
for ep in ["service/api/maint/groups","service/api/maint/projects"]:
  r=requests.get(f"{b}/{ep}?access_token={t}",timeout=15)
  print(f"{ep}: status={r.status_code} body={r.text[:300]}")
