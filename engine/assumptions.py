import json #Bu kütüphane JSON veri alışverişi için yaygın olarak kullanılan bir formattır ve Python'da json modülü bu tür verileri kolayca okuyup yazmak için araçlar sağlar.
from pathlib import Path #Bu kütüphane, dosya yollarını ve dizinleri yönetmek için kullanılır. Path sınıfı, dosya yollarını temsil eder ve dosya işlemleri için çeşitli yöntemler sunar.

from model.config_model import ConfigModel #Bu, model.config_model modülünden ConfigModel sınıfını içe aktarır. Bu sınıf, konfigürasyon verilerini temsil etmek ve doğrulamak için kullanılır.


def loadconfig(config_path: str = "config/config.json") -> ConfigModel:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")
#Bu, belirtilen konfigürasyon dosyasının var olup olmadığını kontrol eder. Eğer dosya bulunamazsa, bir hata mesajı verir.
    with path.open("r", encoding="utf-8") as file:
        raw_config = json.load(file)
        #Bu, konfigürasyon dosyasını açar ve içeriğini bir Python sözlüğüne yükler. Dosya UTF-8 formatında okunur.

    return ConfigModel(**raw_config) 
#Bu, yüklenen konfigürasyon verilerini kullanarak bir ConfigModel nesnesi oluşturur ve döndürür.