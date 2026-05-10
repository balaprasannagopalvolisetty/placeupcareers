import requests
r = requests.post('http://localhost:8000/api/auth/signin', json={'email':'demo@placeup.dev','password':'Password123!'})
token = r.json()['access_token']
s = requests.get('http://localhost:8000/api/user/dashboard-summary', headers={'Authorization': f'Bearer {token}'})
print(f"Status: {s.status_code}")
print(s.json())
