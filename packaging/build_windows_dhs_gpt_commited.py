"""Build only runtime dependencies; exclude collectors, training, reports and unused DBs."""
import subprocess,sys,shutil,json
from pathlib import Path
upstream=Path(sys.argv[1]).resolve();wrapper=Path(__file__).with_name('launch_dhs_gpt_commited.py')
resources=[
 'config.py','Time_Keeper_INTEGRATED_dhs_gpt_commited.html','integrated_dhs_gpt_commited.js','integrated_dhs_gpt_commited.css',
 'services/stations_dhs_gpt_commited.json','services/weather_delay_config_dhs_gpt_commited.json',
 'data/busflow.db','data/busflow_5003.db','data/realtime.db',
 'models/highway_speed_model.pkl','models/congestion_5001a_model.pkl','models/congestion_5003a_model.pkl',
 'analysis/upstream_analysis.xlsx','analysis/station_weekday_hour_average.xlsx','analysis/seat_drop_analysis.xlsx',
 'BusFlow_5003_bus_weather_by_datetime (1).xlsx']
for p in resources:
    if not (upstream/p).is_file():raise FileNotFoundError(p)
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','GTA','--paths',str(upstream),
      '--collect-all','sklearn','--collect-all','holidays','--hidden-import','scipy.special._ufuncs_cxx',
      '--exclude-module','matplotlib','--exclude-module','IPython','--exclude-module','pytest']
for p in resources:args+=['--add-data',str(upstream/p)+';'+str(Path(p).parent)]
args.append(str(wrapper));subprocess.run(args,check=True)
root=Path('dist/GTA')
# Short user instructions, no extra preview files or duplicate technical documents.
(root/'사용방법.txt').write_text('1. ZIP을 압축 해제합니다.\n2. GTA.exe를 더블클릭하면 브라우저가 열립니다.\n3. 실시간 버스는 실행 창의 [API 키 설정]에서 기존 키를 한 번 입력합니다.\n\nPython 설치나 명령어 입력은 필요 없습니다.\n_internal 폴더는 실행에 필요한 파일이므로 그대로 두세요.\n날씨·실시간 버스 조회에는 인터넷이 필요합니다.\n창을 닫으면 서버가 종료됩니다.\n\n출처: wkddnjswkdwkdwkd1-svg/BusFlow\n버전: 185858dc94417403f25581ad24a67a506df17f1c\n실제 API 응답과 예측 정확도는 별도 검증이 필요합니다.\n',encoding='utf-8-sig')
print('BUILD_COMPLETE',sum(f.stat().st_size for f in root.rglob('*') if f.is_file()))
