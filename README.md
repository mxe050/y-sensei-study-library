# Y先生文献の書斎

Y先生が批判的吟味をした論文集です。個人的に行っている非公開版より吟味が甘くなっているかもしれません。クローズドの論文は内容が極めて限定的にしか紹介できないし、オープンの論文でも図などの引用は2－3点以内にしています。

## 公開用の文献を追加する

1. サイトの管理画面で公開用HTMLを選び、プレビューと画像の参照を確認します。公開するHTMLをUTF-8で保存します。埋め込み画像を含む単一HTMLなら、そのファイルだけで掲載できます。
2. 管理画面からGitHubのアップロード画面を開くか、GitHubで [`articles/`](./articles/) を開き、**Add file → Upload files** からHTMLを追加して `main` にコミットします。例として `articles/paper-a.html` は `articles/paper-a.html` のURLで開けます。
3. 別添え画像やCSSがある場合は、`articles/paper-a/index.html` と `articles/paper-a/images/figure1.jpg` のように、HTMLから参照している相対位置を保って一緒にアップロードします。Windowsのローカルパスは、アップロードした画像への相対パスに直します。
4. **Actions → Publish reading shelf** が完了するとトップの目録にも反映されます。外部画像は配信元での公開に依存します。手元で保存した画像を添えた場合は、その相対パスをHTMLに指定してください。

このリポジトリのファイルと履歴は公開されます。コミットする資料は公開用に作成した版を使用してください。

## 新しいHTMLに差し替える

管理画面で差し替える文献を選びます。表示されたGitHubフォルダに、元と同じ名前のHTMLをアップロードしてコミットします。公開URLと目録のIDを引き継ぎ、本文と一覧の内容が更新されます。別添え画像も同じ位置に置きます。以前の版はGitHubのファイル履歴で確認できます。公開ページには目録への戻りリンクが付きます。スマートフォンの画面幅を指定していない資料には表示幅の設定を補い、大きな画像には画面幅に収まる基本スタイルを加えます。GitHubに保存した元ファイルはそのままです。

## 目録の表示を整える

一覧にはHTMLの `title` を使い、指定がなければ最初の `h1`、続いてファイル名を使います。分類と紹介文は任意です。HTMLの `head` に次のように記入できます。

```html
<title>掲載する論文のタイトル</title>
<meta name="study-category" content="臨床疫学">
<meta name="description" content="この論文で検討した問いと、解釈の要点。">
```

一覧に載るのは `articles/` 直下の `.html`・`.htm` と、資料フォルダの `index.html`・`index.htm` です。更新日はHTMLを最後に変更したコミットの日付です。画像や補助ページは同じフォルダ構成で配信します。

## ローカルで確認する

```sh
python3 scripts/build.py --output /tmp/y-study-preview
python3 -m http.server --directory /tmp/y-study-preview 8000
```

`http://localhost:8000/` を開きます。再生成には空の出力先を使います。画像参照がローカルにあるのに実ファイルが見つからない場合はビルドが止まり、ファイル名が表示されます。確認対象は `img` の `src` とSVG `image` の `href` です。

GitHub Pagesの公開元はリポジトリの **Settings → Pages → Build and deployment → Source → GitHub Actions** です。`main` が更新されるたびに `.github/workflows/pages.yml` が公開用ディレクトリを生成し、文献を含む静的サイトを配信します。
