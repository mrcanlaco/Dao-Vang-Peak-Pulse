# Execution Policy Router

Muc tieu cua lop nay la chon **cach vao lenh**, khong thay the model phat hien
tin hieu. Contract thanh cong la gia giam toi thieu 20% tu gia vao trung binh
co trong so trong vong 24 gio.

## Ba policy dong bang

| Policy | Entry offsets | Phan bo | Hard stop | Cua so scale-in | Risk |
|---|---:|---:|---:|---:|---:|
| compact | 0 / +3 / +6% | 20 / 30 / 50% | +12% | 6h | 1.00 |
| balanced | 0 / +5 / +10% | 20 / 30 / 50% | +16% | 6h | 0.75 |
| deep squeeze | 0 / +8 / +14% | 10 / 30 / 60% | +16% | 12h | 0.50 |

Hard stop duoc tinh tu gia signal. Muc tieu -20% duoc tinh lai tu gia trung
binh cua cac leg da khop, khong phai luc nao cung tu gia signal.

## Router v1

Router chi nhan du lieu co tai thoi diem signal:

- signal score/probability;
- data-quality score;
- volatility percentile; neu chua co percentile, dung proxy versioned tu price_volatility_24h;
- squeeze score;
- liquidity score hoac volume 24h.

Thu tu quyet dinh:

1. Volatility thap va squeeze thap: scale_in_compact.
2. Volatility rat cao, squeeze va signal cung cao: scale_in_deep_squeeze.
3. Cac truong hop con lai: scale_in_balanced.
4. Neu volatility vuot safety ceiling, policy van duoc ghi de nghien cuu nhung
   eligible=false.
5. Thieu quality/liquidity cung fail closed (eligible=false).
6. Signal phai dung required_label_version; model v1 chi duoc advisory cho contract v2.

Moi decision ghi router version, feature-schema version, policy version,
subscores, reason codes va checksum. Truong execution_policy_json trong bang
predictions la audit trail de replay va huan luyen.

## Backtest

Ham evaluate_price_path nhan cac thanh OHLC sau signal va mot policy dong bang.
No danh gia:

- leg nao da khop trong cua so scale-in;
- gia vao trung binh thuc te;
- target dong theo cac leg da khop;
- target, stop hay timeout;
- MAE va MFE theo gia vao trung binh.

Neu cung mot thanh gia cham ca stop va target, evaluator tinh stop truoc
(stop_ambiguous). Day la gia dinh bao thu de tranh look-ahead va ket qua qua
lac quan. Khi co du lieu tick/order-book, co the thay evaluator chi tiet hon
nhung phai version hoa.

Chi so so sanh policy:

- hit rate cua muc tieu -20%/24h;
- expected return sau phi, funding va slippage;
- stop rate, timeout rate;
- E2/E3 fill rate;
- MAE p50/p90/p95;
- ket qua theo market-cap tier, liquidity, volatility va squeeze bucket;
- max drawdown cua danh muc va so lenh dong thoi.

Khong chon policy chi theo hit rate. Promotion phai uu tien expected return va
tail risk sau chi phi.

## Dua model AI vao

Selector AI phai implement giao dien PolicySelector va chi duoc tra ve mot
trong cac policy ID da dong bang. Model khong duoc tu tao entry/stop moi trong
runtime.

Quy trinh:

1. selector_mode=rules: rules la champion.
2. selector_mode=shadow_model: model chon challenger; app van dung champion
   va ghi ca hai lua chon.
3. Backtest walk-forward va shadow evaluation tren cac prediction/outcome moi.
4. Chi promotion khi du mau va dat tat ca gate.
5. selector_mode=model: model duoc chon policy; policy va risk guardrail van
   bat bien.

Gate promotion de xuat:

- toi thieu 500 prediction resolved va 50 event duong;
- walk-forward qua it nhat 3 khoang thoi gian, khong random split;
- expected return sau chi phi tang toi thieu 5%;
- hit rate khong giam qua 3 diem phan tram;
- MAE p95 va max drawdown khong xau hon champion;
- khong bucket market-cap/liquidity quan trong nao co suy giam nghiem trong;
- shadow chay toi thieu 14 ngay;
- co the rollback bang config ve rules ngay lap tuc.

Neu model khong san sang, loi, hoac tra policy ID la, router tu dong quay ve
rule champion va ghi reason code.

## Nguyen tac version hoa

Bat ky thay doi nao o threshold, feature, entry, allocation, stop, chronology
hay chi phi backtest deu phai tang version. Khong sua definition cua version
cu. Bao cao backtest phai kem data cutoff, feature schema, router version,
policy versions, fee/slippage assumptions va code commit.
