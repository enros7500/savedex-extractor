// A generic backend adapter: no shell, no Instagram/model logic, no research.
import {spawn} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export function extract(request,{cli,modelDir,workDir,timeoutSeconds=600}) {
  return new Promise((resolve,reject)=>{
    const started=performance.now();
    const child=spawn(cli,['extract','--request','-','--model-dir',modelDir,'--work-dir',workDir,'--timeout-seconds',String(timeoutSeconds),'--log-format','jsonl'],{shell:false,windowsHide:true,stdio:['pipe','pipe','pipe']});
    const stdout=[];const stderr=[];let bytes=0;let logBytes=0;
    const timer=setTimeout(()=>{
      if(process.platform==='win32')spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
      else child.kill('SIGKILL');
      reject(new Error('CLI process exceeded backend deadline'));
    },(timeoutSeconds+20)*1000);
    child.on('error',error=>{clearTimeout(timer);reject(error);});
    child.stdout.on('data',chunk=>{bytes+=chunk.length;if(bytes>16*1024*1024){child.kill();reject(new Error('CLI output too large'));}else stdout.push(chunk);});
    child.stderr.on('data',chunk=>{if(logBytes<65536){stderr.push(chunk);logBytes+=chunk.length;}});
    child.on('close',code=>{
      clearTimeout(timer);
      try {
        const result=JSON.parse(Buffer.concat(stdout).toString('utf8'));
        if(result.schema_version!=='3.0.0'||result.task!=='extract')throw new Error('Unsupported CLI content contract');
        if((code===0)!==(result.status==='success')||(code===2)!==(result.status==='partial'))throw new Error('CLI exit/status mismatch');
        resolve({exitCode:code,result,stderr:Buffer.concat(stderr).toString('utf8'),wallSeconds:(performance.now()-started)/1000});
      } catch(error) {reject(new Error('CLI protocol failure: '+error.message));}
    });
    child.stdin.on('error',()=>{});
    child.stdin.end(JSON.stringify(request),'utf8');
  });
}

if(process.argv[1]&&path.resolve(process.argv[1])===path.resolve(fileURLToPath(import.meta.url))) {
  const [cli,modelDir,workDir,url,outputDir]=process.argv.slice(2);
  if(!cli||!modelDir||!workDir||!url||!outputDir)throw new Error('Usage: node backend-client.mjs CLI MODEL_DIR WORK_DIR URL OUTPUT_DIR');
  const id=new URL(url).pathname.split('/').filter(Boolean).at(-1);
  const request={schema_version:'3.0.0',request_id:'backend_'+id,url};
  const response=await extract(request,{cli,modelDir,workDir});
  await mkdir(outputDir,{recursive:true});
  await writeFile(path.join(outputDir,id+'.result.json'),JSON.stringify(response.result,null,2)+'\n');
  await writeFile(path.join(outputDir,id+'.backend.json'),JSON.stringify({exitCode:response.exitCode,wallSeconds:response.wallSeconds,stdoutWasSingleJSON:true,request,stderr:response.stderr},null,2)+'\n');
  console.log(JSON.stringify({id,exitCode:response.exitCode,status:response.result.status,items:response.result.items.length,wallSeconds:response.wallSeconds}));
}
