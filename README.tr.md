<p align="center">
  <img src="docs/images/logo.svg" width="128" height="128" alt="Bilge logosu">
</p>

<h1 align="center">Windows ve Linux için Bilge</h1>

<p align="center">
  Windows ve Linux için Türkçe ve İngilizce konuşan bir sesli asistan.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="Lisans: GPL-3.0"></a>
  <img src="https://img.shields.io/badge/Windows-10%2F11-0078D4?logo=windows" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/Linux-AppImage-FCC624?logo=linux&logoColor=black" alt="Linux AppImage">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
</p>

<p align="center">
  <a href="README.md">English</a> · <b>Türkçe</b>
</p>

<p align="center">
  <img src="docs/images/tr/hud-confirm.png" width="380" alt="Bilge takvime etkinlik eklemeden önce soruyor">
</p>

[Mac için Bilge](https://github.com/coderssociety/bilge-assistant)'nin kardeşidir: aynı asistan, aynı kurallar
(“Bilge” de, riskli bir şey yapmadan önce sorar). Mac sürümü yalnızca Apple'a özgü parçalardan oluştuğu için
Python ile yeniden yazıldı.

Mac sürümünden farklı olarak dil modeli bilgisayarında da çalışabilir, internetteki bir API de olabilir; kurulumda
seçilir:

| | Bu bilgisayarda | İnternetten (API) |
|---|---|---|
| Dil modeli | Ollama, LM Studio, llama.cpp | OpenAI, Anthropic, Google Gemini, OpenRouter, Groq, DeepSeek |

API anahtarları düz bir dosyada değil, sistemin anahtar deposunda durur (Windows'ta Kimlik Bilgileri Yöneticisi,
Linux'ta Secret Service).

## Durum

Beş aşamanın hepsi tamam; en yeni sürüm 0.1.2.

1. **Çekirdek** (tamam): Mac sürümündeki Türkçe ve İngilizce ayrıştırıcılar, aynı test örnekleriyle; onaylı ve
   istem enjeksiyonuna karşı kurallı araç çağıran ajan; denemek için yazılı sohbet.
2. **Ses** (tamam): uyandırma kelimesi ya da kısayol; konuşma tanıma (işlemcide ya da ekran kartında Whisper, ya da
   OpenAI veya Groq API'si); Supertonic-3 sesi; araya girebilmen için yankı giderme; sahibinin sesini tanıma.
3. **Linux araçları** (tamam): uygulamalar, ses seviyesi, müzik çalarlar, dosyalar ve belgeler, yazma ve dikte,
   zamanlayıcılar, takvim ve anımsatıcılar, LibreOffice Calc, sistem ayarları.
4. **Windows araçları** (tamam): aynıları, ayrıca Excel, Outlook e-postası ve Outlook takvimi ile görevleri.
5. **Uygulama** (tamam): bildirim alanı simgesi, konuşmayı gösteren köşe penceresi, ayarlar, ilk kurulum, Windows
   yükleyicisi ve Linux AppImage'ı.

## Ekran görüntüleri

<table>
  <tr>
    <td width="50%"><img src="docs/images/tr/setup.png" alt="Kurulumun ilk adımı: dil seçimi"></td>
    <td width="50%"><img src="docs/images/tr/settings-general.png" alt="Genel ayarlar"></td>
  </tr>
  <tr>
    <td align="center">Kurulum dil seçimiyle başlar: Türkçe ya da English.</td>
    <td align="center">Uyandırma kelimesi, dinleme kısayolu, köşe penceresi ve güncelleme denetimi.</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/tr/settings-model.png" alt="Model ayarları"></td>
    <td width="50%"><img src="docs/images/tr/settings-recognition.png" alt="Tanıma ayarları"></td>
  </tr>
  <tr>
    <td align="center">Bu bilgisayarda bir model (LM Studio, Ollama, llama.cpp) ya da bir API.</td>
    <td align="center">Whisper işlemcide mi ekran kartında mı, ne kadar hızlı, ve senin sesin.</td>
  </tr>
  <tr>
    <td colspan="2" align="center"><img src="docs/images/tr/hud-answer.png" width="380" alt="Bilge hava durumu sorusunu cevaplıyor"></td>
  </tr>
  <tr>
    <td colspan="2" align="center">Köşe penceresi ne duyduğunu ve ne cevap verdiğini gösterir.</td>
  </tr>
</table>

Görüntüler Windows 11'den; Linux'ta pencereler masaüstünün kendi görünümünü alır. `scripts/screenshots.py`
görüntüleri uygulamanın gerçek pencerelerinden, örnek ayarlarla yeniden üretir.

## Kurulum

- **Windows 10/11 (64 bit):** sürümler sayfasından `Bilge-Setup-<sürüm>.exe`'yi çalıştır. Yalnızca senin kullanıcın
  için, yönetici izni istemeden kurulur ve Bilge'yi Windows'la birlikte başlatabilir. Yükleyici imzasız olduğundan
  Windows ilk açılışta uyarır: **Ek bilgi → Yine de çalıştır**.
- **Linux:** `Bilge-<sürüm>-x86_64.AppImage`'ı (ya da `aarch64`) indir, çalıştırılabilir yap ve aç. x86_64 için glibc
  2.34 ya da daha yenisi (Ubuntu 22.04+, Debian 12+, Fedora 36+), arm64 için 2.39 gerekir. GNOME'da bildirim alanı
  simgesi için AppIndicator eklentisi gerekir (Ubuntu'da var); yoksa Bilge küçük bir pencere açar.

İlk açılışta kurulum dili, dil modelini ve konuşma tanımayı sorar, ses modellerini indirir (1-2 GB). Sonra Bilge
bildirim alanında durur: “Bilge” de ve isteğini söyle. `Bilge.AppImage cli …` ve `bilge-cli.exe` aşağıdaki komut
satırını verir.

## Kaynaktan denemek

Python 3.12 ve [uv](https://docs.astral.sh/uv/) gerekir.

```bash
uv sync
uv run bilge use lmstudio <model kimliği>  # ya da: openai, anthropic, gemini, openrouter, groq, deepseek, ollama
uv run bilge key openai                    # yalnızca API sağlayıcıları; sistemin anahtar deposunda saklanır
uv run bilge chat                          # yazarak
uv run bilge listen                        # sesle; ilk seferde ses modellerini indirir
uv sync --extra app && uv run bilge-app    # kurulum ve ayarlarıyla bildirim alanı uygulaması
```

`uv run bilge models` seçili sağlayıcının modellerini listeler.

## Bilge'yi çağırmak

“Bilge” de ya da Ayarlar → Genel'de seçtiğin dinleme kısayoluna bas; Bilge konuşurken basarsan susar. Kısayol
seçiliyken uyandırma kelimesi kapatılabilir; o zaman kısayola basılana kadar hiçbir şey yazıya dökülmez. Windows ve
X11 masaüstleri kısayolu doğrudan alır; Wayland'de masaüstü bir kez onayını ister (KDE Plasma 5.27+, GNOME 48+); KDE'de
sonradan Sistem Ayarları → Kısayollar'dan değiştirilebilir. Bunun olmadığı yerde ve isteği alıp kendisi tuş atamayan
Hyprland'de, `Bilge --listen` komutuna (tam hâli ayarlarda yazar) masaüstünün kendi klavye ayarlarından bir kısayol ata.

## Konuşma tanıma

Bilgisayardaki Whisper işlemcide; CUDA 12 ve cuDNN 9 kuruluysa NVIDIA kartta CUDA ile; ya da yükleyicilerin içinde
gelen Vulkan'lı whisper.cpp ile her ekran kartında (AMD, Intel ya da NVIDIA) çalışır. Otomatik seçenek, varsa ayrı
bir ekran kartını kullanır; Ayarlar → Tanıma'dan işlemciye gömülü kartı ya da yalnızca işlemciyi de seçebilirsin.
Ekran kartında model ayrıca yaklaşık 870 MB indirilir. Oradaki “Hızı ölç” her yerde bir isteğin süresini ölçer;
hangisini seçeceğini sayılar gösterir. Büyük model 10, 30 ya da 60 dakika kullanılmayınca bellekten de
çıkarılabilir; Bilge adını yine duyar, yalnızca ardından gelen ilk istek model yeniden yüklenirken birkaç saniye
bekler.

Arka planından yüksek hiçbir ses içermeyen bir kayıt yazıya dökülmez; Whisper'ın sessizlikte uydurduğu altyazı
cümleleri (“Altyazı M.K.”, “Thanks for watching!”) yazdıklarından çıkarılır.

## Güncellemeler

Bilge günde bir kez GitHub'a en yeni sürümü sorar; daha yenisi varsa bildirim alanı menüsünde sayfasının
bağlantısıyla görünür. Kendiliğinden hiçbir şey indirilmez ya da kurulmaz. Ayarlar → Genel'den kapatılabilir.

## Neler yapar

| | Örnekler | Linux'ta | Windows'ta |
|---|---|---|---|
| Uygulamalar | “Firefox'u aç”, “hesap makinesini kapat”, “açık uygulamalar neler” | menü girdileri, `gio` | Başlat menüsü |
| Ses | “sesi yüzde 30 yap”, “müziği durdur”, “ne çalıyor” | `wpctl`, `pactl` ya da `amixer`; MPRIS çalarlar | Core Audio; sistemin medya denetimleri |
| Dosyalar | “kira sözleşmesini bul”, “son indirdiğim PDF'i özetle”, “eski faturayı çöpe at” | freedesktop çöp kutusu | Geri Dönüşüm Kutusu |
| Yazma | “şunu yaz: …”, “dikte modunu başlat” | `xdotool` (X11), `wtype` ya da `ydotool` (Wayland) | yerleşik |
| Takvim | “yarın neler var”, “cuma 10'da diş hekimi ekle”, “süt almayı işaretle” | CalDAV ya da bir iCal adresi | aynısı ya da Outlook |
| Tablo | “D3'e B2 ile B1'i topla”, “C5'e 1250 yaz”, “geri al” | LibreOffice Calc (`python3-uno`) | Excel ya da LibreOffice Calc |
| E-posta | “okunmamış e-postalarım”, “Ahmet'e yarın geleceğimi yaz” | | Outlook |
| Sistem | “ekranı kilitle”, “karanlık modu aç”, “Wi-Fi'ı kapat”, “ekran görüntüsü al”, “pil kaç” | `loginctl`, `gsettings` ya da Plasma, `nmcli`, masaüstünün ekran görüntüsü aracı | yerleşik |
| Pano | “panoda ne var”, “seçili metni çevir”, “bunu kopyala” | `wl-clipboard`, `xclip` ya da `xsel` | yerleşik |
| Diğer | zamanlayıcılar ve alarmlar, site ve arama açma, günlük özet | | |

Dosyaları çöpe atmak, uygulama kapatmak, dolu bir hücrenin üzerine yazmak, takvime eklemek ya da Wi-Fi'ı kapatmak
önce sorulur; Bilge'nin başka bir yerde okuduğu metni taşıyabilecek her şey de öyle. Bir e-posta, gideceği adresle
birlikte gönderilmeden önce sesli okunur. Terminallerde, kod düzenleyicilerde, uzak masaüstlerinde, sanal
makinelerde ve parola yöneticilerinde yazma reddedilir. Wayland'deki GNOME öndeki pencereyi başka programlara
söylemediği için orada Bilge yazmadan önce sorar.

### Takvim bağlamak

```bash
uv run bilge calendar caldav https://cloud.example.org/remote.php/dav --user ayse   # Nextcloud, iCloud, Fastmail…
uv run bilge calendar ics                   # salt okunur: örn. Google Takvim'in "iCal biçiminde gizli adresi"
uv run bilge calendar outlook               # Windows: Outlook açıkken Outlook'un takvimi ve görevleri
uv run bilge calendar off
```

Parola (hizmet sunuyorsa uygulama parolası kullan) ve gizli adres gizli olarak yazılır ve sistemin anahtar
deposunda saklanır. CalDAV'a, aynı bilgisayardaki bir sunucu dışında yalnızca HTTPS üzerinden bağlanılır.

## Geliştirme

```bash
uv run pytest
uv run ruff check src tests && uv run ruff format --check src tests
```

`bench/`, Mac sürümünde yönlendirmeyi ölçmek için kullanılan komut kümelerini içerir. `scripts/linux-check` tüm
test paketini Ubuntu'da, ayrıca gerçek programları (yazma, pano, ses, bir MPRIS çalar, bildirimler, LibreOffice
Calc…) ekransız bir masaüstünde süren testlerle birlikte çalıştırır:

```bash
docker build -t bilge-linux-check scripts/linux-check
docker run --rm -v "$PWD":/src:ro bilge-linux-check
```

Yükleyiciler bir sürüm etiketinde `.github/workflows/release.yml` ile derlenir: PyInstaller (`packaging/bilge.spec`),
Windows'ta Inno Setup (`packaging/windows/bilge.iss`) ve Docker'da derlenen bir AppImage (`packaging/linux`). İkisi de
Vulkan'la derlenmiş whisper.cpp sunucusunu içerir (`packaging/whisper`); onsuz bir derleme Whisper'ı yalnızca
işlemcide ya da NVIDIA kartta çalıştırır. Kaynaktan bir kartla denemek için `PATH`'e bir `whisper-server` koy ya da
`BILGE_WHISPER_SERVER` ile göster.

Windows'ta `tests/windows` aynısını oturum açılmış masaüstünde yapar (birkaç pencere açıp kapatır):

```powershell
$env:BILGE_REAL_DESKTOP = 1; uv run pytest tests/windows
```

## Lisans

GPL-3.0, bkz. [LICENSE](LICENSE).
