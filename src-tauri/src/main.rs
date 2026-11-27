// Kelime Ustası — macOS masaüstü kabuğu.
//
// Uygulamanın tamamı web ön ucundadır (React, ../src); bu kabuk yalnızca onu
// macOS'un kendi WebKit'iyle (WKWebView) yerel bir pencerede açar. Ön uç hiçbir
// Tauri komutu çağırmaz ve ağa çıkmaz; veriler pencerenin LocalStorage'ında,
// uygulama kimliğine (`com.erebb.kelimeustasi`) bağlı kalıcı depoda tutulur.

// Windows'ta sürüm derlemesinde fazladan konsol penceresi açılmasın.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::menu::{AboutMetadata, Menu, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Runtime};

const APP_NAME: &str = "Kelime Ustası";

/// Türkçe uygulama menüsü.
///
/// Düzen menüsü süs değil: macOS'ta WKWebView içindeki metin kutularında
/// ⌘C / ⌘V / ⌘X / ⌘A kısayolları ancak bu öğeler menüde varsa çalışır.
/// Uygulamanın "Metin Yapıştır" ile içe aktarması buna dayanır.
///
/// Her platformda derlenir (Linux'ta `cargo check` tipleri doğrulasın),
/// ama yalnızca macOS'ta takılır.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
fn build_menu<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<Menu<R>> {
    let about = AboutMetadata {
        name: Some(APP_NAME.into()),
        version: Some(app.package_info().version.to_string()),
        comments: Some("Kendi kelime listelerinle oyunlaştırılmış öğrenme.".into()),
        ..Default::default()
    };

    let app_menu = Submenu::with_items(
        app,
        APP_NAME,
        true,
        &[
            &PredefinedMenuItem::about(app, Some("Kelime Ustası Hakkında"), Some(about))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, Some("Kelime Ustası'nı Gizle"))?,
            &PredefinedMenuItem::hide_others(app, Some("Diğerlerini Gizle"))?,
            &PredefinedMenuItem::show_all(app, Some("Tümünü Göster"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::quit(app, Some("Kelime Ustası'ndan Çık"))?,
        ],
    )?;

    let edit_menu = Submenu::with_items(
        app,
        "Düzen",
        true,
        &[
            &PredefinedMenuItem::undo(app, Some("Geri Al"))?,
            &PredefinedMenuItem::redo(app, Some("Yinele"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, Some("Kes"))?,
            &PredefinedMenuItem::copy(app, Some("Kopyala"))?,
            &PredefinedMenuItem::paste(app, Some("Yapıştır"))?,
            &PredefinedMenuItem::select_all(app, Some("Tümünü Seç"))?,
        ],
    )?;

    let window_menu = Submenu::with_items(
        app,
        "Pencere",
        true,
        &[
            &PredefinedMenuItem::minimize(app, Some("Küçült"))?,
            &PredefinedMenuItem::maximize(app, Some("Büyüt"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::close_window(app, Some("Pencereyi Kapat"))?,
        ],
    )?;

    Menu::with_items(app, &[&app_menu, &edit_menu, &window_menu])
}

fn main() {
    let builder = tauri::Builder::default();

    #[cfg(target_os = "macos")]
    let builder = builder.menu(build_menu);

    builder
        .run(tauri::generate_context!())
        .expect("Kelime Ustası başlatılamadı");
}
