# 暮らしのしるべ Editorial V2 ローカル記事

白背景で実装した、ポータブル電源比較記事の独立ローカルプレビューです。

## 起動

リポジトリルートで実行:

```bash
python3 -m http.server 4173 --directory artifacts/local-article-editorial-v2
```

ブラウザで次を開く:

```text
http://127.0.0.1:4173/
```

## 注意

- 商品名、仕様値、出典はすべてローカル表示確認用の合成fixtureです。
- CTAはページ内の注意書きへ遷移し、外部サイトを開きません。
- `editorial-hero.png` はアートディレクション確認用です。公開時は権利と商品同定を確認した実商品画像へ差し替えます。
- `index.html` と `article.css` だけで動作し、外部フォント・JavaScript・ネットワーク通信は使いません。
