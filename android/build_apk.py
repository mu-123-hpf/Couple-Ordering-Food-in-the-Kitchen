from pathlib import Path
import os,sys,json,subprocess,zipfile,hashlib,secrets,shutil
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
SDK=PROJECT/'work/android-sdk'
TOOLS=SDK/'build-tools/35.0.0'
JAR=SDK/'platforms/android-35/android.jar'
JAVA=Path(os.environ.get('JAVA_HOME',r'D:\Program Files\Java\jdk-23'))/'bin'
CONFIG=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
BUILD=ROOT/'build';BUILD.mkdir(exist_ok=True)
SIGN=ROOT/'signing';SIGN.mkdir(exist_ok=True)
OUT=PROJECT/'out';OUT.mkdir(exist_ok=True)
records=[]
def run(args,env=None):
    args=[str(x) for x in args]
    result=subprocess.run(args,cwd=ROOT,capture_output=True,env=env)
    for label,raw in [('stdout',result.stdout),('stderr',result.stderr)]:
        (BUILD/('command-'+str(len(records)+1)+'.'+label+'.bin')).write_bytes(raw)
        try:text=raw.decode('utf-8')
        except UnicodeDecodeError:text=raw.decode('gbk',errors='replace')
        setattr(result,label,text)
    records.append({'command':args,'cwd':str(ROOT),'stdout':result.stdout,'stderr':result.stderr,'exit':result.returncode})
    (BUILD/'commands.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RUN='+args[0]+' EXIT='+str(result.returncode),flush=True)
    if result.stdout:print(result.stdout,flush=True)
    if result.stderr:print(result.stderr,flush=True)
    if result.returncode:raise SystemExit(result.returncode)
    return result
for path in [JAVA/'java.exe',JAVA/'javac.exe',JAVA/'keytool.exe',TOOLS/'aapt2.exe',TOOLS/'zipalign.exe',TOOLS/'lib/d8.jar',TOOLS/'lib/apksigner.jar',JAR]:
    if not path.is_file():raise SystemExit('Missing build dependency: '+str(path))
source=ROOT/'src/com/example/lovekitchen/MainActivity.java'
assert ('"'+CONFIG['baseUrl']+'"') in source.read_text(encoding='utf-8'),'Base URL differs from Android config'
compiled=BUILD/'resources.zip'
if compiled.exists():compiled.unlink()
run([TOOLS/'aapt2.exe','compile','--dir',ROOT/'res','-o',compiled])
gen=BUILD/'generated';gen.mkdir(exist_ok=True)
base=BUILD/'resources.apk'
run([TOOLS/'aapt2.exe','link','-o',base,'-I',JAR,'--manifest',ROOT/'AndroidManifest.xml','--java',gen,'--auto-add-overlay',compiled])
classes=BUILD/'classes';classes.mkdir(exist_ok=True)
sources=[*sorted((ROOT/'src').rglob('*.java')),*sorted(gen.rglob('*.java'))]
run([JAVA/'javac.exe','-encoding','UTF-8','--release','8','-classpath',JAR,'-d',classes,*sources])
classzip=BUILD/'classes.zip'
with zipfile.ZipFile(classzip,'w',zipfile.ZIP_DEFLATED) as z:
    for item in classes.rglob('*.class'):z.write(item,item.relative_to(classes).as_posix())
dex=BUILD/'dex';dex.mkdir(exist_ok=True)
run([JAVA/'java.exe','-cp',TOOLS/'lib/d8.jar','com.android.tools.r8.D8','--lib',JAR,'--min-api',str(CONFIG['minSdk']),'--output',dex,classzip])
unsigned=BUILD/'unsigned.apk';shutil.copy2(base,unsigned)
with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as z:
    for item in dex.glob('*.dex'):z.write(item,item.name)
aligned=BUILD/'aligned.apk'
run([TOOLS/'zipalign.exe','-f','-p','4',unsigned,aligned])
keystore=SIGN/'couple-kitchen-release.p12'
passwordfile=SIGN/'keystore-password.txt'
if keystore.exists() and not passwordfile.exists():raise SystemExit('Signing password is missing; do not replace existing update key')
if not passwordfile.exists():
    passwordfile.write_text(secrets.token_urlsafe(36),encoding='utf-8');passwordfile.chmod(0o600)
env=os.environ.copy();env['KITCHEN_APK_KEY_PASSWORD']=passwordfile.read_text(encoding='utf-8').strip()
if not keystore.exists():
    run([JAVA/'keytool.exe','-genkeypair','-keystore',keystore,'-storetype','PKCS12','-alias','couple-kitchen','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Couple Kitchen Release, OU=Mobile, O=Couple Kitchen, C=CN','-storepass:env','KITCHEN_APK_KEY_PASSWORD','-keypass:env','KITCHEN_APK_KEY_PASSWORD','-noprompt'],env)
    keystore.chmod(0o600)
apk=OUT/('couple-kitchen-'+CONFIG['versionName']+'.apk')
run([JAVA/'java.exe','-jar',TOOLS/'lib/apksigner.jar','sign','--ks',keystore,'--ks-key-alias','couple-kitchen','--ks-pass','env:KITCHEN_APK_KEY_PASSWORD','--key-pass','env:KITCHEN_APK_KEY_PASSWORD','--out',apk,aligned],env)
verified=run([JAVA/'java.exe','-jar',TOOLS/'lib/apksigner.jar','verify','--verbose','--print-certs',apk])
run([TOOLS/'zipalign.exe','-c','-p','4',apk])
badging=run([TOOLS/'aapt2.exe','dump','badging',apk])
raw=apk.read_bytes()
with zipfile.ZipFile(apk) as z:
    assert z.testzip() is None
    assert 'AndroidManifest.xml' in z.namelist() and 'classes.dex' in z.namelist()
    assert CONFIG['baseUrl'].encode() in z.read('classes.dex')
assert 'com.example.lovekitchen' in badging.stdout
result={'path':str(apk),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'config':CONFIG,'signatureVerified':True,'zipAlignmentVerified':True,'deviceInstallVerified':False,'commands':str(BUILD/'commands.json')}
(BUILD/'build-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(OUT/'couple-kitchen-1.0.0.apk.sha256').write_text(result['sha256']+'  '+apk.name+'\n',encoding='utf-8')
print('SIGNED_APK='+str(apk));print('SHA256='+result['sha256']);print('BYTES='+str(len(raw)));print('BASE_URL='+CONFIG['baseUrl']);print('APK_SIGNATURE=VERIFIED');print('DEVICE_INSTALL=NOT_TESTED_NO_DEVICE')
