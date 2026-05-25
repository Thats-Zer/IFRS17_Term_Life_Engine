# IFRS 17 Vadeli Hayat Değerleme Motoru

**İncelenmesi, sorgulanması, test edilmesi ve geliştirilmesi için tasarlanmış portfolio-grade bir IFRS 17 Term Life valuation engine.**

Bu proje, **vadeli hayat sigortası** için hazırlanmış modüler bir Python değerleme motorudur. Aktüerya Bilimleri son sınıf CV/portföy projesi olarak tasarlanmıştır. Motor; poliçe bazlı projeksiyon, nakit akışı modelleme, iskonto, BEL, Risk Adjustment, CSM roll-forward, onerous sözleşme testi, IFRS 17 tarzı gruplama, senaryo analizi ve audit çıktıları üretir.

Projenin amacı, aktüeryal modelleme bilgisini, Python mühendisliğini ve IFRS 17 farkındalığını temiz ve mülakatlarda anlatılabilir bir yapı içinde göstermektir.

> Akademik kapsam: Bu proje eğitim ve portföy amacıyla hazırlanmıştır. Üretim ortamında kullanılacak gerçek bir IFRS 17 sistemi değildir. Üretim seviyesi için resmi metodoloji onayı, varsayım yönetimi, kalibrasyon, kontroller, mutabakatlar, veri geçmişi ve bağımsız validasyon gerekir.

## Bu Repository Neden Var?

IFRS 17 uygulamaları çoğu zaman incelenmesi zor, kapalı, karmaşık ve yüksek governance gerektiren sistemlerdir. Bu repo bunun tersini amaçlar: eğitim odaklı, konfigürasyonla yönetilebilen ve üzerinde oynanabilen bir değerleme sandbox'ı sunar.

Kullanıcılar `config/config.json` üzerinden varsayımları değiştirebilir, motoru çalıştırabilir, ara çıktıları inceleyebilir ve varsayımların projection, cashflows, BEL, RA, CSM, grouping, scenarios, diagnostics ve audit dosyalarına nasıl aktığını gözlemleyebilir.

Amaç production seviyesinde bir IFRS 17 sistemi sunmak değildir. Amaç temel mekanikleri görünür, test edilebilir ve tartışılabilir hale getirmektir.

## Proje Özeti

Bu proje, **Term Life** portföyleri için **basitleştirilmiş IFRS 17 çerçevesi** altında çalışan, Python tabanlı modüler bir aktüeryal değerleme motorudur. Projeksiyon tabloları, nakit akışları, BEL, RA, CSM, gruplama çıktıları, senaryo sonuçları ve audit çıktıları üretir. Mimari; **modülerlik, izlenebilirlik, test edilebilirlik, açıklanabilirlik ve denetlenebilirlik** üzerine kuruludur.

Temel amacı **CV/portföy** seviyesinde IFRS 17 muhakemesini, aktüeryal modellemeyi, yazılım mühendisliği disiplinini ve model governance farkındalığını göstermektir. Proje, bilinçli olarak **incelenebilir, sorgulanabilir, test edilebilir ve geliştirilebilir** şekilde tasarlanmıştır.

## Ne Yapar?

- Sentetik vadeli hayat poliçe verisi üretir.
- Her poliçeyi yıl bazında projekte eder.
- Mortalite, lapse, survival, gider, prim, reasürans ve karşı taraf riski varsayımlarını uygular.
- Dönem başı ve dönem sonu iskonto faktörlerini ayrı kullanarak bugünkü değer hesaplar.
- **BEL** değerini yükümlülük-pozitif yaklaşımla hesaplar.
- Basitleştirilmiş stokastik **Risk Adjustment** hesaplar.
- Başlangıç **CSM**, onerous loss, CSM release, finance cost ve kapanış CSM hesaplar.
- Portföy, yıllık kohort, kârlılık grubu ve risk grubu bazında IFRS 17 tarzı gruplama yapar.
- Mortalite, lapse, gider ve iskonto oranı şokları gibi senaryo analizleri çalıştırır.
- CSV, Excel, audit report, assumption snapshot, BEL diagnostics ve run registry çıktıları üretir.
- Hesaplama kimlikleri ve aktüeryal mantık için otomatik testler içerir.

## Bu Proje Nedir?

- Portfolio-grade bir aktüeryal mühendislik projesi
- Basitleştirilmiş IFRS 17 Term Life valuation engine
- Modüler Python tabanlı değerleme framework’ü
- Öğrenme odaklı ve challengeable bir model
- BEL, RA, CSM, gruplama, senaryo, diagnostics, reconciliation ve audit çıktılarının gösterimi
- Aktüeryal muhakeme, teknik uygulama ve governance farkındalığını sergilemek için tasarlanmış bir çalışma

## Bu Proje Ne Değildir?

- Üretim seviyesinde bir IFRS 17 sistemi değildir
- Regülasyonel raporlama aracı değildir
- Resmi muhasebe/aktüeryal danışmanlık değildir
- Şirket seviyesinde IFRS 17 modellerinin yerine geçmez
- Gerçek şirket deneyim verisine kalibre edilmemiştir (aksi belirtilmedikçe)

## Aktüeryal Mantık

Motor aşağıdaki basitleştirilmiş ölçüm yapısını kullanır:

- **Projeksiyon:** poliçe-yıl grid'i, güncel yaş, in-force durumu, mortalite, lapse ve survival.
- **Nakit akışları:** primler, ölüm tazminatları, surrender benefit, operasyonel giderler, reasürans ceding/recovery ve karşı taraf default maliyeti.
- **İskonto:** prim benzeri akışlarda dönem başı, hasar/gider benzeri akışlarda dönem sonu iskonto faktörü.
- **BEL:** yükümlülük-pozitif olarak outflow bugünkü değeri eksi inflow bugünkü değeri.
- **RA:** finansal olmayan risk için basitleştirilmiş stokastik confidence-level yaklaşımı.
- **CSM:** BEL prim girişlerini zaten içerdiği için `max(-(BEL + RA), 0)`.
- **Onerous loss:** `max(BEL + RA, 0)`.
- **Gruplama:** portföy, yıllık kohort, kârlılık grubu ve risk özellikleri.

Detaylı formül dokümantasyonu:

- `FORMULAS/To_Inform.txt`
- `FORMULAS/Bilgilendirme.txt`
- `DOCUMENTS/ACTUARIAL_METHODOLOGY_VALIDATION_REPORT.md`

## Projeyi Challenge Et

Bu repository şeffaf ve teknik olarak sorgulanabilir şekilde tasarlanmıştır. İnceleyenlerin varsayımları, formülleri, mimariyi ve çıktıları sorgulaması teşvik edilir. Özellikle şunları challenge edebilirsiniz:

- BEL sign konvansiyonu
- Cashflow zamanlama varsayımları
- Prim, hasar, gider ve reasürans yaklaşımı
- Risk Adjustment metodolojisi
- CSM yaklaşımı
- IFRS 17 gruplama mantığı
- Senaryo varsayımları
- Diagnostic ve reconciliation çıktıları
- Model governance kararları
- Test kapsamı
- Kod mimarisi ve bakım yapılabilirliği

Bu repository’nin amacı üretim seviyesinde IFRS 17 uyumu iddia etmek değil; **aktüeryal muhakeme, model governance farkındalığı ve yazılım mühendisliği disiplinini** şeffaf biçimde göstermektir.

## Proje Yapısı

```text
config/      Model varsayımları ve çalışma konfigürasyonu
data/        Örnek mortalite tablosu
DOCUMENTS/   Metodoloji ve validasyon raporu
engine/      Ana hesaplama modülleri
FORMULAS/    Formül ve metodoloji notları
model/       Pydantic konfigürasyon modeli
tests/       Otomatik validasyon ve regresyon testleri
outputs/     Üretilen çıktılar, git tarafından izlenmez
main.py      Uçtan uca motor çalıştırıcı
```

## Ana Modüller

```text
engine/projection.py   Master data ve poliçe-yıl projeksiyonu
engine/curves.py       İskonto ve lapse eğrileri
engine/cashflows.py    Prim, hasar, gider, reasürans ve PV nakit akışları
engine/bel.py          Best Estimate Liability
engine/ra.py           Risk Adjustment
engine/csm.py          CSM hesaplama ve roll-forward
engine/grouping.py     IFRS 17 tarzı gruplama ve onerous sınıflandırma
engine/scenarios.py    Senaryo analizi
engine/outputs.py      CSV, Excel, audit ve registry çıktıları
engine/audit.py        Varsayım snapshot, audit report ve run metadata

## Teknik Öne Çıkanlar

- **Modüler akış:** assumptions/config → projection → cashflows → BEL → RA → CSM → grouping → scenarios → outputs/audit
- **Pydantic** tabanlı konfigürasyon doğrulama
- **Pandas / NumPy** hesaplama katmanı
- **pytest** validasyon testleri
- **logging** ve audit izleri
- **CSV, Excel ve JSON çıktıları**
- **deterministik assumption snapshot / hash**
- **senaryo analizi**
- **opsiyonel BEL diagnostics**

### BEL Öne Çıkanlar

- **Liability-positive konvansiyon:** BEL = PV(outflows) - PV(inflows)
- **Poliçe bazında breakdown:**
	- bel_per_policy
	- pv_bel_outflows
	- pv_bel_inflows
	- pv_claims
	- pv_surrender_benefits
	- pv_expenses
	- pv_reinsurance_ceding
	- pv_reinsurance_recovery
	- pv_counterparty_default_cost
	- pv_premiums
	- pv_death_benefits
	- bel_sign_explanation
- **Diagnostics:** build_bel_diagnostic_summary(), _report_bel_diagnostics(), get_last_bel_diagnostic_summary()
- **Audit JSON çıktıları:** audit_report.json, bel_diagnostics.json
- **Governance geliştirmesi:** Base BEL diagnostics senaryo overwrite riskine karşı açıkça korunur
```

## Kurulum

Windows PowerShell:

```powershell
git clone https://github.com/Thats-Zer/IFRS17_Term_Life_Engine.git
cd IFRS17_Term_Life_Engine
python -m pip install -r requirements
```

## Çalıştırma

```powershell
python main.py
```

Varsayılan konfigürasyon dosyası:

```text
config/config.json
```

## Çıktılar

Motor çalıştırıldığında `outputs/` altında şu dosyalar üretilir:

```text
master_results.csv
projection_results.csv
bel_results.csv
ra_results.csv
csm_results.csv
group_results.csv
scenario_results.csv
ifrs17_term_life_projection.xlsx
assumption_snapshot.json
audit_report.json
bel_diagnostics.json
run_registry.csv
```

Üretilen çıktılar git tarafından izlenmez. Böylece repository kaynak kod, testler, varsayımlar ve dokümantasyon odaklı kalır.

## Testler

```powershell
python -m pytest -q
```

Test kapsamı:

- import ve smoke testleri
- projeksiyon ve iskonto eğrisi kontrolleri
- nakit akışı zamanlama kontrolleri
- BEL mutabakat kontrolleri
- CSM formül kontrolleri
- CSM release dağılım kontrolleri
- senaryo şoku davranış kontrolleri
- gruplama kontrolleri
- audit snapshot ve run registry kontrolleri
- diagnostics kapalıyken davranış kontrolleri
- base diagnostics sahipliği (senaryo overwrite kontrolü)

## Diagnostics ve Governance

- Diagnostics opsiyoneldir ve `config.json` içindeki `enable_bel_diagnostics` ile kontrol edilir.
- BEL diagnostic summary, `audit_report.json` içinde `bel_diagnostics` olarak yer alır.
- Ayrıca `bel_diagnostics.json` ayrı dosya olarak yazılır.
- Base run diagnostics, `calculate_bel()` sonrası hemen yakalanır ve output katmanına
	açıkça aktarılır; böylece senaryo çalışmaları base çıktıyı overwrite etmez.
- Senaryo çalışmaları diagnostics’i varsayılan olarak kapatır.

## CV İçin Örnek Açıklama

**IFRS 17 Vadeli Hayat Değerleme Motoru**  
Vadeli hayat sigortası için basitleştirilmiş IFRS 17 mantığıyla çalışan modüler bir Python değerleme motoru geliştirdim. Proje; poliçe bazlı projeksiyon, mortalite/lapse modelleme, nakit akışı üretimi, BEL, stokastik Risk Adjustment, CSM roll-forward, onerous sözleşme testi, IFRS 17 tarzı gruplama, senaryo analizi, audit snapshot ve otomatik validasyon testlerini içerir.

## CV / LinkedIn İçin Kısa Öneri

**English:**
Developed a portfolio-grade IFRS 17 Term Life valuation engine in Python, designed as a transparent and challengeable actuarial engineering project with modular BEL/RA/CSM calculations, scenario analysis, diagnostics, reconciliation checks, and audit-ready JSON outputs.

**Turkish:**
Python ile portfolio-grade bir IFRS 17 Term Life valuation engine geliştirdim. Proje; BEL/RA/CSM hesaplamaları, senaryo analizleri, reconciliation kontrolleri, diagnostic raporlar ve audit-ready JSON çıktılarıyla incelenebilir ve geliştirilebilir bir aktüeryal mühendislik çalışması olarak tasarlandı.

## Teknoloji

- Python 3.11+
- pandas
- NumPy
- Pydantic
- pytest
- openpyxl

## Sınırlamalar

Bu proje sentetik veri ve basitleştirilmiş varsayımlar kullanır. Üretim seviyesi bir IFRS 17 platformunun yerine geçmez. Özellikle:

- Model basitleştirilmiş IFRS 17 çerçevesi kullanır.
- Varsayımlar varsayılan olarak gerçek şirket verisine kalibre değildir.
- Mortalite, lapse, gider ve senaryo varsayımları gerçek verilerle değiştirilmedikçe örnektir.
- RA metodolojisi basitleştirilmiş olabilir.
- CSM yaklaşımı eğitim/portfolio-grade kapsamındadır ve üretim IFRS 17 karmaşıklıklarını tam kapsamayabilir.
- Reasürans held muhasebesi basitleştirilmiştir.
- Coverage units, unlocking, transition, VFA/PAA/GMM ayrımları gerçek kullanımda genişletme gerektirebilir.
- Çıktılar öğrenme, gösterim ve portföy değerlendirme amaçlıdır.

## Lisans

Detaylar için `LICENSE` dosyasına bakınız.
