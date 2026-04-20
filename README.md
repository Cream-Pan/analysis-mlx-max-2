<div id="top"></div>

# ファイル解析アプリ

Excel / CSV 形式の計測データを読み込み，**MLX90632** と **MAX30102** に関する評価指標を自動計算・可視化する Web アプリケーションである．  
研究・実験用途を想定し，**ログファイルあり／なしの両方に対応**しながら，タスク区間ごとの比較や固定時間区間ごとの比較を行えるように設計している．

## 使用技術一覧

<p style="display: inline">
  <img src="https://img.shields.io/badge/-Python-3776AB.svg?logo=python&style=for-the-badge&logoColor=white">
  <img src="https://img.shields.io/badge/-Flask-000000.svg?logo=flask&style=for-the-badge">
  <img src="https://img.shields.io/badge/-Pandas-150458.svg?logo=pandas&style=for-the-badge">
  <img src="https://img.shields.io/badge/-scikit--learn-F7931E.svg?logo=scikit-learn&style=for-the-badge&logoColor=white">
  <img src="https://img.shields.io/badge/-Chart.js-FF6384.svg?logo=chartdotjs&style=for-the-badge&logoColor=white">
  <img src="https://img.shields.io/badge/-JavaScript-F7DF1E.svg?logo=javascript&style=for-the-badge&logoColor=black">
</p>

## 目次

1. [概要](#概要)
2. [主な機能](#主な機能)
3. [想定する入力ファイル](#想定する入力ファイル)
4. [Version 2.0 での改善点](#version-20-での改善点)
5. [ディレクトリ構成](#ディレクトリ構成)
6. [セットアップ](#セットアップ)
7. [実行方法](#実行方法)
8. [設計上の工夫](#設計上の工夫)

## 概要

本アプリは，センサデータと真値データを時間同期し，区間ごとの誤差指標を自動算出する研究支援ツールである．  
主に以下の評価を対象としている．

- **MLX評価**  
  体温真値と MLX90632 の出力値を比較し，MAE・RMSE・各平均値を区間ごとに算出する．
- **MLX修正後評価**  
  補正後の MLX データを用いて，再評価を行う．
- **MAX評価**  
  ECG，PPG_BPM，PPG_fin_BPM を比較し，元データと 1 分平均の両方で誤差を評価する．
- **ファイル内容表示**  
  アップロードした CSV / Excel ファイルの先頭部分を簡易確認する．

また，解析結果はそのまま **PNG 保存**できるため，実験結果の共有や記録にも向いている．

<p align="right">(<a href="#top">トップへ</a>)</p>

---

## 主な機能

### 1．解析モードの切り替え
以下の 4 つのモードを切り替えて使用できる．

- ファイル内容を表示
- MLX評価
- MAX評価
- MLX修正後評価

### 2．ログファイルあり／なし両対応
- **ログあり**  
  `log.csv` に含まれる `Task_Name` と `Timestamp` を基準に，実験タスク単位で解析する．
- **ログなし**  
  任意の区切り分数を指定し，固定時間区間ごとに解析する．

### 3．MLX 生データファイルの柔軟な解決
`mlx_evaluation` では，固定ファイル名だけでなく，ファイル名キーワードをもとに対象ファイルを自動解決できる．  
これにより，実験条件ごとにファイル名が少し異なる場合でも，同じ処理系で評価を回せる．

### 4．時刻同期と誤差計算
複数系列の時刻をそろえたうえで比較対象ペアを作り，以下を算出する．

- MAE
- RMSE
- 平均体温
- 平均 Object_C
- 平均 Ambient_C

### 5．結果の保存
各解析結果ブロックを PNG として保存できる．  
研究ノートや発表資料用の図として流用しやすい．

<p align="right">(<a href="#top">トップへ</a>)</p>

---

## 想定する入力ファイル

### MLX評価
固定必須:
- `body_temperature.csv`
- `log.csv`（ログありの場合）

追加で以下のいずれかを使用:
- `3-Device_Measurement.xlsx`
- `MLX_*_Measurement*.csv`

### MLX修正後評価
固定必須:
- `body_temperature.csv`
- `mlx_re.csv`
- `log.csv`（ログありの場合）

### MAX評価
固定必須:
- `ecg.csv`
- `PPG_BPM.csv`
- `PPG_fin_BPM.csv`
- `log.csv`（ログありの場合）

### ファイル内容表示
任意の CSV / Excel ファイルを選択可能

<p align="right">(<a href="#top">トップへ</a>)</p>

---

## Version 2.0 での改善点

Version 1.0 では，解析条件やタスク名がコード内に固定で埋め込まれていた．  
Version 2.0 では，以下の改善を行った．

### 1．設定の外出し
`config.json` に以下を集約した．

- 解析タイプごとの必須ファイル
- 必須ファイルの補足情報
- MLX のシート候補名
- MLX 評価用ファイル候補名
- MLX 評価用ファイル名キーワード
- タスク名一覧

### 2．ログあり／なし両対応
`log.csv` がある場合は実験タスク単位で解析し，ない場合は指定分数で固定時間区間を作成するようにした．

### 3．MLX ファイル解決の柔軟化
`3-Device_Measurement.xlsx` 固定ではなく，候補名やキーワードに基づいて MLX 生データファイルを自動選択できるようにした．

### 4．UI の整理
解析モードをラジオボタンで選択し，必要ファイルや補足情報を画面上に表示するようにした．  
ログなし時は区切り分数入力欄を表示し，操作フローを明確化した．

<p align="right">(<a href="#top">トップへ</a>)</p>

---

## ディレクトリ構成

```text
.
├── app.py            # Flask バックエンド，解析処理本体
├── app.js            # フロントエンドロジック
├── index.html        # UI 構造
├── style.css         # UI スタイル
├── config.json       # 解析設定ファイル
├── requirements.txt  # 依存ライブラリ
└── README.md         # 本ファイル
````

<p align="right">(<a href="#top">トップへ</a>)</p>

---

## セットアップ

### 1．依存ライブラリのインストール

```bash id="x6nhl4"
pip install -r requirements.txt
```

### 2．ファイル配置

`app.py` と同じディレクトリに，以下のファイルを配置する．

* `index.html`
* `app.js`
* `style.css`
* `config.json`

<p align="right">(<a href="#top">トップへ</a>)</p>

---

## 実行方法

### 1．Flask サーバー起動

```bash id="qtv96z"
python app.py
```

### 2．フロントエンドを開く

`index.html` は `file://` ではなく，ローカルサーバー経由で開くことを推奨する．
たとえば VSCode の Live Server などを利用する．

### 3．解析手順

1. ファイルを選択する
2. 実行したい解析モードを選択する
3. 必要に応じて `log.csv` の使用有無を切り替える
4. ログなしの場合は区切り分数を指定する
5. `解析する` を押す

<p align="right">(<a href="#top">トップへ</a>)</p>

---

## 設計上の工夫

### 1．研究データ向けの柔軟な時刻処理

日時文字列だけでなく，Excel シリアル値や持続時間表現にも対応し，異なる計測系のデータを同一アプリ内で扱えるようにした．

### 2．実験ログを基準にした区間評価

`log.csv` を用いることで，単なる固定時間平均ではなく，実験プロトコルに沿った区間ごとの評価を行えるようにした．

### 3．ファイル名揺れへの耐性

MLX 生データについては固定名依存を避け，候補名とキーワードに基づく解決処理を導入した．
これにより，実験ごとにファイル名が少し異なる場合でも同じ解析系で扱える．

### 4．軽量な結果共有

評価結果をその場で PNG 化できるようにし，解析結果の記録や資料化を容易にした．

### 5．設定とロジックの分離

解析対象や探索条件を `config.json` に外出しし，コード変更なしで設定だけを差し替えられる構成にした．
これにより，再利用性と保守性を高めている．

<p align="right">(<a href="#top">トップへ</a>)</p>

<p align="center">
  <img src="./image.png" width="600px" alt="参考写真">
</p>

開発者情報
Name: Takato Ishii

Portfolio: https://takato-ishii.vercel.app/