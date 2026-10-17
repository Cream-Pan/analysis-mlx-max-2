# 回帰テスト

`python -B -m unittest discover -s tests -v` は，個人データを使わない軽量テストを実行します．

軽量テストでは，ログ時刻の並べ替えと隣接境界の区間化，短い最終区間，時刻不正・境界不足，プレビュー範囲のStart／End処理も確認します．生成CSVの列・行・値は，実測回帰テストで保存済みCSVと比較します．

実測データによる再現テストは，`tests/real_data/` に次の ZIP がある場合だけ実行します．このフォルダは `.gitignore` で除外しており，CSV や個人データを Git に含めません．データファイルは ZIP 内に保持するため，PC 上の元フォルダの場所が変わってもテストは影響を受けません．

- `mlx_ayane.zip`，`mlx_shion.zip`：body temperature，MLX，ログ
- `ppg_hr_ayane.zip`，`ppg_hr_shion.zip`：PPG 生データと期待する HR 出力
- `ppg_acc_ayane.zip`，`ppg_acc_shion.zip`：Fin／耳たぶの PPG 生データと期待する Summary／Detail CSV
- `ppg_compare_day1.zip`，`ppg_compare_day2.zip`：左右 HR CSV とタスクログ

ZIP 内の CSV 名はテストコードで指定した名前を維持してください．実測回帰テストは次のコマンドで実行できます．

```powershell
python -B -m unittest discover -s tests -p test_real_data_regression.py -v
```

