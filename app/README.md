# Court Signal app (Flutter)

First time (run inside this `app` folder):

    flutter create . --project-name court_signal --platforms android,ios,web
    flutter pub get
    flutter run                 # Android phone or emulator
    flutter run -d chrome       # quick test in the browser

`flutter create .` adds the android/ios/web folders and keeps the files already here.

For a release Android build, add this line inside `<manifest>` in
`android/app/src/main/AndroidManifest.xml` (debug runs already have it):

    <uses-permission android:name="android.permission.INTERNET"/>

In the app: Settings -> enter your server address (for example https://your-app.onrender.com),
the API key if your server has one, then Test connection and Save.
