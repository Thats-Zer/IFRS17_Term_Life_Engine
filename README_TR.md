# IFRS 17 Vadeli Hayat Değerleme Motoru

Bu proje, **vadeli hayat sigortası** için hazırlanmış modüler bir Python değerleme motorudur. Aktüerya Bilimleri son sınıf CV/portföy projesi olarak tasarlanmıştır. Motor; poliçe bazlı projeksiyon, nakit akışı modelleme, iskonto, BEL, Risk Adjustment, CSM roll-forward, onerous sözleşme testi, IFRS 17 tarzı gruplama, senaryo analizi ve audit çıktıları üretir.

Projenin amacı, aktüeryal modelleme bilgisini, Python mühendisliğini ve IFRS 17 farkındalığını temiz ve mülakatlarda anlatılabilir bir yapı içinde göstermektir.

> Akademik kapsam: Bu proje eğitim ve portföy amacıyla hazırlanmıştır. Üretim ortamında kullanılacak gerçek bir IFRS 17 sistemi değildir. Üretim seviyesi için resmi metodoloji onayı, varsayım yönetimi, kalibrasyon, kontroller, mutabakatlar, veri geçmişi ve bağımsız validasyon gerekir.

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
- CSV, Excel, audit report, assumption snapshot ve run registry çıktıları üretir.
- Hesaplama kimlikleri ve aktüeryal mantık için otomatik testler içerir.

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

- `Formulas/To_Inform.txt`
- `Formulas/Bilgilendirme.txt`
- `docs/ACTUARIAL_METHODOLOGY_VALIDATION_REPORT.md`

## Proje Yapısı

```text
config/      Model varsayımları ve çalışma konfigürasyonu
data/        Örnek mortalite tablosu
engine/      Ana hesaplama modülleri
model/       Pydantic konfigürasyon modeli
tests/       Otomatik validasyon ve regresyon testleri
Formulas/    Formül ve metodoloji notları
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

## CV İçin Örnek Açıklama

**IFRS 17 Vadeli Hayat Değerleme Motoru**  
Vadeli hayat sigortası için basitleştirilmiş IFRS 17 mantığıyla çalışan modüler bir Python değerleme motoru geliştirdim. Proje; poliçe bazlı projeksiyon, mortalite/lapse modelleme, nakit akışı üretimi, BEL, stokastik Risk Adjustment, CSM roll-forward, onerous sözleşme testi, IFRS 17 tarzı gruplama, senaryo analizi, audit snapshot ve otomatik validasyon testlerini içerir.

## Teknoloji

- Python 3.11+
- pandas
- NumPy
- Pydantic
- pytest
- openpyxl

## Sınırlamalar

Bu proje sentetik veri ve basitleştirilmiş varsayımlar kullanır. Üretim seviyesi bir IFRS 17 platformunun yerine geçmez. Özellikle:

- RA ve CSM metodolojileri eğitim amaçlı yaklaşımlardır.
- Mortalite, lapse, gider ve reasürans varsayımları üretim kalibrasyonuna sahip değildir.
- Gruplama IFRS 17 tarzındadır, ancak sentetik portföy verisine dayanır.
- Governance ve audit çıktıları hafif metadata seviyesindedir, tam onay iş akışı değildir.
- Finansal tablo dipnotları ve resmi aktüeryal validasyon raporları mevcut kapsam dışındadır.

## Lisans

Detaylar için `LICENSE` dosyasına bakınız.
