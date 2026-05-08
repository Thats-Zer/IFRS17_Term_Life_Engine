# IFRS 17 Term Life Engine

## Türkçe

### Proje Özeti
Bu proje, **term life (vadeli hayat)** sigortası ürünleri için IFRS 17 prensiplerine uygun şekilde nakit akış projeksiyonu ve değerleme yapan modüler bir Python uygulamasıdır. Aşağıdaki temel bileşenleri üretir:

- **Projection (Poliçe × Yıl)**: Yaş-yıl grid’i, mortalite, lapse ve survival oranları
- **Cashflows**: Prim girişleri, tazminat/masraf çıkışları, net nakit akışı
- **Discounting**: Discount curve ve iskontolu nakit akışları
- **BEL (Best Estimate Liability)**: En iyi tahmin yükümlülüğü
- **RA (Risk Adjustment)**: Risk ayarlaması (modelde tanımlanan yaklaşıma göre)
- **CSM (Contractual Service Margin)**: Başlangıç CSM ve roll-forward
- **IFRS 17 Gruplama & Onerous Testi**: Onerous sözleşme testi ve gruplandırma
- **Senaryo Analizi**: Mortalitenin artması, lapse artışı, gider artışı, iskonto oranı şoku gibi senaryolar

> Not: Bu proje **portföy/akademik** amaçlıdır. Gerçek üretim ortamı için veri doğrulama, kalibrasyon, governance ve audit trail gereklidir.

### Proje Yapısı
- `config/` : Model parametreleri (`config.json`)
- `data/` : Örnek mortalite tablosu
- `engine/` : Hesaplama modülleri (projection, cashflows, bel, ra, csm, grouping, scenarios, outputs)
- `model/` : Pydantic config modeli
- `outputs/` : Üretilen çıktı dosyaları (CSV/Excel)

### Kurulum
Windows PowerShell:

```powershell
cd "C:\Users\sevva\Desktop\BUSEFERSON\IFRS17_Term_Life_Engine"
python -m pip install -r requirements
```

### Çalıştırma
```powershell
python main.py
```

### Çıktılar
Çalışma sonunda `outputs/` altında tipik olarak:
- `master_results.csv`
- `projection_results.csv`
- `bel_results.csv`
- `ra_results.csv`
- `csm_results.csv`
- `scenario_results.csv`
- `ifrs17_term_life_projection.xlsx` (Excel satır limiti nedeniyle büyük tablolar “preview/özet” olarak yazılabilir)

### Testler
```powershell
python -m pytest -q
```

---

## English

### Overview
This project is a modular Python valuation engine for **term-life insurance** aligned with key IFRS 17 concepts. It produces:

- **Projection (Policy × Year)**: age-year grid, mortality, lapse, survival
- **Cashflows**: premiums, claims/expenses, net cashflows
- **Discounting**: discount curve and discounted cashflows
- **BEL (Best Estimate Liability)**
- **RA (Risk Adjustment)** (as implemented in the model)
- **CSM (Contractual Service Margin)**: initial CSM and roll-forward
- **IFRS 17 Grouping & Onerous Testing**
- **Scenario Analysis**: mortality up, lapse up, expense up, discount shock, etc.

> Note: This repository is intended for **academic/portfolio** use. Production use would require additional validation, calibration, governance, and audit trail capabilities.

### Repository Structure
- `config/` : model parameters (`config.json`)
- `data/` : sample mortality table
- `engine/` : calculation modules (projection, cashflows, bel, ra, csm, grouping, scenarios, outputs)
- `model/` : Pydantic configuration model
- `outputs/` : generated outputs (CSV/Excel)

### Installation
```powershell
cd "C:\Users\sevva\Desktop\BUSEFERSON\IFRS17_Term_Life_Engine"
python -m pip install -r requirements
```

### Run
```powershell
python main.py
```

### Outputs
Generated under `outputs/`, typically:
- `master_results.csv`
- `projection_results.csv`
- `bel_results.csv`
- `ra_results.csv`
- `csm_results.csv`
- `scenario_results.csv`
- `ifrs17_term_life_projection.xlsx` (large tables may be exported as preview/summary due to Excel row limits)

### Tests
```powershell
python -m pytest -q
```

---

## Tech Stack
- Python 3.11+
- Pandas / NumPy
- Pydantic

## License
See `LICENSE`.
