"""지역 임금효과 직접 측정 — 부산 vs 서울, 구성 효과와 가격 효과 분해.

임금  : 사업체노동력조사 시도×산업(6)×규모(14), 2025 상용월급여액
가중치: 전국사업체조사 시도×산업(20)×종사자규모(10), 2024 종사자수
두 표의 분류가 달라 산업 6군·규모 6구간으로 맞춘다.
규모 `20-49명`은 임금표 경계(10~29 / 30~99)에 걸쳐 두 시나리오로 민감도를 본다.
"""
import warnings; warnings.filterwarnings("ignore")
import itertools
import pandas as pd

IND = {  # 사업체표 산업 → 임금표 6군
    "광업(05~08)": "광업.제조업(B,C)", "제조업(10~34)": "광업.제조업(B,C)",
    "건설업(41~42)": "건설업(F)",
    "도매및소매업(45~47)": "도소매ㆍ음식숙박업(G,I)", "숙박및음식점업(55~56)": "도소매ㆍ음식숙박업(G,I)",
    "전기,가스,증기및공기조절공급업(35)": "전기ㆍ운수ㆍ통신ㆍ금융업(D,H,J,K)",
    "운수및창고업(49~52)": "전기ㆍ운수ㆍ통신ㆍ금융업(D,H,J,K)",
    "정보통신업(58~63)": "전기ㆍ운수ㆍ통신ㆍ금융업(D,H,J,K)",
    "금융및보험업(64~66)": "전기ㆍ운수ㆍ통신ㆍ금융업(D,H,J,K)",
    "수도,하수및폐기물처리,원료재생업(36~39)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "부동산업(68)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "전문,과학및기술서비스업(70~73)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "사업시설관리,사업지원및임대서비스업(74~76)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "공공행정,국방및사회보장행정(84)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "교육서비스업(85)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "보건업및사회복지서비스업(86~87)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "예술,스포츠및여가관련서비스업(90~91)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
    "협회및단체,수리및기타개인서비스업(94~96)": "사업ㆍ개인ㆍ공공서비스업(E,L~S)",
}
BANDS = ["1~4인", "5~9인", "10~29인", "30~99인", "100~299인", "300인이상"]
SZ = {"1-4명": "1~4인", "5-9명": "5~9인", "10-19명": "10~29인", "50-99명": "30~99인",
      "100-299명": "100~299인", "300-499명": "300인이상", "500-999명": "300인이상",
      "1000명이상": "300인이상"}

w = pd.read_csv("out/KOSIS_시도산업규모별_임금.csv")
e = pd.read_csv("out/KOSIS_시도산업규모별_사업체.csv")
e = e[e.산업.isin(IND)].copy()
e["산업6"] = e.산업.map(IND)

def weights(city, mid_to):                      # 20-49명을 어디로 보낼지
    m = dict(SZ); m["20-49명"] = mid_to
    x = e[(e.시도 == city) & e.규모.isin(m)].copy()
    x["규모6"] = x.규모.map(m)
    return x.groupby(["산업6", "규모6"]).종사자수.sum()

def wages(city):
    x = w[(w.시도 == city) & (w.규모.isin(BANDS)) & (w.산업 != "전산업")]
    return x.set_index(["산업", "규모"]).월급여액

print("■ A. 같은 산업·같은 규모 칸에서 부산은 서울의 몇 %인가 (2025 상용월급여액)")
bs, sl = wages("부산"), wages("서울")
tab = pd.DataFrame({"부산": bs, "서울": sl})
tab["부산/서울%"] = tab.부산 / tab.서울 * 100
piv = tab["부산/서울%"].unstack("규모")[BANDS]
piv.index = [i.split("(")[0] for i in piv.index]
print(piv.round(1).to_string())
print(f"\n  칸 평균 {tab['부산/서울%'].mean():.1f}%  ·  36칸 중 부산이 낮은 칸 "
      f"{(tab['부산/서울%'] < 100).sum()}/{tab['부산/서울%'].notna().sum()}")

print("\n■ B. 부산-서울 임금 격차 분해")
for mid in ["10~29인", "30~99인"]:
    wb_, ws_ = weights("부산", mid), weights("서울", mid)
    idx = bs.index.intersection(wb_.index).intersection(ws_.index).intersection(sl.index)
    b_w, s_w = wb_[idx] / wb_[idx].sum(), ws_[idx] / ws_[idx].sum()
    actual_b, actual_s = (b_w * bs[idx]).sum(), (s_w * sl[idx]).sum()
    counter = (b_w * sl[idx]).sum()             # 부산 구성 × 서울 임금
    gap = actual_s - actual_b
    price, comp = counter - actual_b, actual_s - counter
    print(f"  [20-49명 → {mid}]")
    print(f"    부산 {actual_b:>10,.0f}원   서울 {actual_s:>10,.0f}원   격차 {gap:>9,.0f}원 ({gap/actual_s*100:.1f}%)")
    print(f"      가격 효과(같은 칸인데 덜 줌) {price:>9,.0f}원 ({price/gap*100:5.1f}%)")
    print(f"      구성 효과(산업·규모가 다름)  {comp:>9,.0f}원 ({comp/gap*100:5.1f}%)")
