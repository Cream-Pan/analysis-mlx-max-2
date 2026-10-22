# ファイル解析アプリ

Excel / CSV 形式の計測データを読み込み，**MLX90632** と **MAX30102**
に関する評価指標を自動計算・可視化する Web アプリケーションである．\
研究・実験用途を想定し，**ログファイルあり／なしの両方に対応**しながら，タスク区間ごとの比較や固定時間区間ごとの比較を行えるように設計している．

## 使用技術一覧

## 目次

1.  [概要](#概要)
2.  [主な機能](#主な機能)
3.  [想定する入力ファイル](#想定する入力ファイル)
4.  [Version 3.0 での改善点](#version-30-での改善点)
5.  [ディレクトリ構成](#ディレクトリ構成)
6.  [セットアップ](#セットアップ)
7.  [実行方法](#実行方法)
8.  [設計上の工夫](#設計上の工夫)
9.  [解析方法の詳細](#解析方法の詳細)

## 概要

本アプリは，センサデータと基準データを時間同期し，区間ごとの評価指標を自動算出する研究支援ツールである．

対象機能：

-   **MLX評価**\
    体温真値と MLX90632 の出力値を比較し，MAE・RMSE・平均値を算出する．
-   **MLX修正後評価**\
    補正後 MLX データを再評価する．
-   **MAX評価**\
    ECG，PPG_BPM，PPG_fin_BPM を比較する．
-   **PPG→HR解析**\
    PPG 波形から HR を推定し，窓ごとの推定状態を確認する．
-   **PPG＋ACC解析**\
    PPG と加速度から Motion Artifact
    を評価し，HR利用可能率や精度指標を算出する．
-   **PPG脈波解析**\
    ログのタスク時刻，または指定した時間区間を30秒ごとに分け，HR，RMSSD，SDNN，pPPI50を算出する．表にはタスクごとの平均値を示す．
-   **ファイル内容表示**\
    CSV / Excel データを時間軸または行番号で可視化する．

解析結果は PNG 保存できる．

各機能の入力条件，解析手順，出力値，品質判定，制約は，次の説明書にまとめている．

## 解析方法の詳細

| 機能 | 説明 |
| --- | --- |
| ファイル内容表示 | [ファイル内容表示の方法](docs/file-preview.md) |
| MLX評価 | [MLX評価の方法](docs/mlx-evaluation.md) |
| MLX修正後評価 | [MLX修正後評価の方法](docs/mlx-reevaluation.md) |
| MAX評価 | [MAX評価の方法](docs/max-evaluation.md) |
| PPG→HR変換 | [PPG→HR変換の方法](docs/ppg-to-hr.md) |
| PPG解析 | [PPG解析の方法](docs/ppg-analysis.md) |
| PPG＋ACC解析 | [PPG＋ACC解析の方法](docs/ppg-acc-analysis.md) |
| PPG脈波解析 | [PPG脈波解析の方法](docs/ppg-prv-analysis.md) |

------------------------------------------------------------------------

## 主な機能

### 1．解析モードの切り替え

-   ファイル内容表示
-   MLX評価
-   MAX評価
-   MLX修正後評価
-   PPG→HR解析
-   PPG＋ACC解析
-   PPG脈波解析

### 2．ログファイルあり／なし対応

-   ログあり：`log.csv` の `Task_Name` と `Timestamp`
    を基準にタスク単位で解析する．
-   ログなし：指定した時間区間で解析する．

### 3．MLX時間軸再構築

`RecvJST` と `SensorElapsed_ms` を利用し，センサ基準の時刻を再構築する．

処理：

    再構築時刻 = RecvJST の初期値 + SensorElapsed_ms

ログありの場合は `Start` から `End` までの範囲を抽出する．

### 4．PPG＋ACC解析

10 秒窓，5 秒オーバーラップで解析し，

-   HR推定状態
-   Motion Artifact
-   HR_Usable
-   PPG と ACC の周波数一致
-   コヒーレンス

を評価する．

### 5．結果保存

解析結果を PNG 保存できる．\
PPG＋ACC解析では窓詳細 CSV を出力できる．

------------------------------------------------------------------------

## 想定する入力ファイル
各解析モードで受け付ける入力を以下に示す．ログを使用する場合は，`*_log.csv` 形式のログファイルを1つ選択する．ログには `Task_Name` と `Timestamp` の列が必要である．

### MLX評価

- `body_temperature.csv`：2列以上
- `3-Device_Measurement.xlsx` または `mlx` を含む CSV：8列以上
- ログファイル：任意

### MLX修正後評価

- `body_temperature.csv`：2列以上
- `mlx_re.csv`：9列以上
- ログファイル：任意

### MAX評価

- `ecg.csv`：`Timestamp`，`HeartRate_BPM`
- `PPG_BPM.csv` と `PPG_fin_BPM.csv`：`RecvJST`，`HR_BPM`
- ログファイル：任意

### PPG→HR変換

- PPG生データ CSV：`RecvJST`，`IR_Value`，`RED_Value`，`Accel_X_mg`，`Accel_Y_mg`，`Accel_Z_mg`，`SensorElapsed_ms`
- ログファイル：使用しない

### PPG解析

- `*_HR.csv` を2つ以上：各ファイルに `RecvJST`，`HR_BPM`
- ログファイル：任意

### PPG脈波解析

- PPG CSVを1つ以上：各ファイルに `RecvJST`，`IR_Value`
- ログファイル：任意．使用時はログの `Task_Name` と `Timestamp` からタスク区間を作る．
- ログを使用しない場合は，区切り分数と開始オフセットを指定する．解析時間を空欄にすると，ファイル末尾まで解析する．

### PPG＋ACC解析

- ファイル名に `fin` を含むFin PPG生データ CSVを1つ
- ファイル名に `fin` を含まない耳たぶ PPG生データ CSVを1つ
- 各生データ CSV に `RecvJST`，`IR_Value`，`RED_Value`，`Accel_X_mg`，`Accel_Y_mg`，`Accel_Z_mg`，`SensorElapsed_ms`
- ログファイル：必須

### ファイル内容表示

- 表示対象の CSV または Excel：任意
- ログファイル：タスク境界表示に使う場合のみ必要

------------------------------------------------------------------------

## Version 3.0 での改善点

### 1．PPG＋ACC解析機能追加

-   加速度との周波数比較
-   コヒーレンス解析
-   Motion Artifact判定
-   HR利用可能率評価

を追加した．

### 2．PPG品質情報追加

窓ごとに以下を保存する．

-   Window_Start
-   Window_End
-   Window_Center
-   HR_BPM_Window
-   HR_Status
-   HR_Usable

### 3．時間同期処理改善

センサ内部時間を利用した再構築時刻に対応した．

### 4．ファイル表示改善

-   時間軸表示
-   ログ境界表示
-   表示列切替
-   拡大縮小

に対応した．

------------------------------------------------------------------------

## ディレクトリ構成

``` text
.
├── .gitignore
├── .python-version
├── app.py
├── app.js
├── js/
│   ├── actions/
│   │   └── file-export.js
│   ├── charts/
│   │   ├── chart-range-controls.js
│   │   └── file-preview.js
│   └── results/
│       ├── evaluations.js
│       ├── ppg-acc-analysis.js
│       ├── ppg-acc-actions.js
│       ├── ppg-acc-table-rows.js
│       ├── ppg-acc-formatters.js
│       ├── ppg-comparison.js
│       ├── ppg-to-hr.js
│       └── ppg-hr-analysis.js
├── index.html
├── style.css
├── config.json
├── requirements.txt
├── start_app.bat
├── vendor/
│   ├── chartjs/
│   ├── chartjs-adapter-date-fns/
│   ├── chartjs-plugin-annotation/
│   ├── chartjs-plugin-zoom/
│   ├── html2canvas/
│   ├── SHA256SUMS.txt
│   └── README.md
├── services/
│   ├── __init__.py
│   ├── settings.py
│   ├── common.py
│   ├── time_utils.py
│   ├── log_service.py
│   ├── file_preview_service.py
│   ├── mlx_service.py
│   ├── max_service.py
│   ├── hr_compare_service.py
│   ├── ppg_service.py
│   ├── ppg_prv_service.py
│   ├── ppg_acc_service.py
│   └── security.py
├── docs/
│   ├── file-preview.md
│   ├── mlx-evaluation.md
│   ├── mlx-reevaluation.md
│   ├── max-evaluation.md
│   ├── ppg-to-hr.md
│   ├── ppg-analysis.md
│   ├── ppg-acc-analysis.md
│   └── ppg-prv-analysis.md
├── tests/
│   ├── test_app_security.py
│   ├── test_input_validation.py
│   ├── test_regression_basics.py
│   ├── test_time_log_boundaries.py
│   ├── test_real_data_regression.py
│   └── README.md
└── README.md
```

------------------------------------------------------------------------

## セットアップ

CPython 3.11 以上を使用する．依存ライブラリのバージョンは `requirements.txt` に固定している．Windows では，次の手順で仮想環境を作成してから起動する．

``` powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

アップロード容量は `config.json` の `upload_limits` で設定する．初期値は1ファイルあたり256 MiB，リクエスト全体で512 MiBである．同じファイル名（大文字・小文字の違いを含む）を複数選択した場合は，解析前にエラーを返す．

安全性のため，開発サーバーは `127.0.0.1` のみで待ち受け，デバッグモードと CORS は既定で無効にする．画面が必要とするファイルだけを配信し，それ以外のアプリ内ファイルへのアクセスは拒否する．`/upload` は同一オリジンか許可済みオリジンからのみ受け付ける．別オリジンから利用する構成に限り，`VITBUDS_CORS_ORIGINS` に許可するオリジンをカンマ区切りで指定する（例：`https://example.org`）．`*` は指定できない．公開環境では開発サーバーを使わず，本番用 WSGI サーバーと HTTPS を設定する．グラフ関連ライブラリもローカル配信するため，アプリ起動後の画面利用にCDN接続は不要である．

`app.py` と同じディレクトリに以下を配置する．

-   `index.html`
-   `app.js`
-   `style.css`
-   `config.json`

------------------------------------------------------------------------

## 実行方法

``` bash
python app.py
```

その後，ローカルサーバー経由で `index.html` を開く．

解析手順：

1.  ファイル選択
2.  解析モード選択
3.  必要条件設定
4.  解析実行

------------------------------------------------------------------------

## 設計上の工夫

### 1．柔軟な時刻処理

異なるセンサの時刻形式に対応し，統一した時間軸で解析する．

### 2．ログ基準評価

実験ログを利用し，タスク単位の評価を可能にする．

### 3．品質を考慮した解析

PPG＋ACC解析により，モーションアーチファクトを考慮した評価を可能にする．

### 4．設定とロジックの分離

解析条件を `config.json` に外出しし，再利用性を向上させる．

設定ファイルは `services/settings.py` から一度読み込み，画面処理と解析サービスで同じ設定を参照する．`services/common.py` はアップロードと入力検証を担当し，ログ区間処理は `services/log_service.py`，時刻変換は `services/time_utils.py` に分離する．

------------------------------------------------------------------------

## 開発者情報

Name: Takato Ishii

Portfolio: https://takato-ishii.vercel.app/
