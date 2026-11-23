#!/usr/bin/env python3
import argparse, hashlib, json, logging, math, os, random
from pathlib import Path
import pyarrow.parquet as pq
import torch
import torch.distributed as dist
from torch.utils.data import IterableDataset, DataLoader

WINDOW_SIZE=25; MAX_WINDOWS=3
STATE_TO_ID={'C':5,'H':6,'E':7}; BIO_IDS=(5,6,7)
CLS_ID=2; SEP_ID=3; MASK_ID=4; UNK_ID=1; VOCAB_SIZE=8
COL='secondary_structure_spaced'

def args():
 p=argparse.ArgumentParser()
 p.add_argument('--dataset-dir',type=Path,default=Path(__file__).resolve().parents[3] / 'data' / 'data_uniref50' / 'bert_mlm_dataset')
 p.add_argument('--model-dir',type=Path,default=Path(__file__).resolve().parents[3] / 'model' / 'secondary_bert')
 p.add_argument('--output-json',type=Path,default=None)
 p.add_argument('--batch-size',type=int,default=256); p.add_argument('--parquet-batch-rows',type=int,default=8192)
 p.add_argument('--mlm-probability',type=float,default=.15); p.add_argument('--seed',type=int,default=42)
 p.add_argument('--max-val-proteins',type=int,default=None); p.add_argument('--logging-steps',type=int,default=500)
 return p.parse_args()

def init_dist():
 rank=int(os.getenv('RANK','0')); local=int(os.getenv('LOCAL_RANK','0')); world=int(os.getenv('WORLD_SIZE','1'))
 if torch.cuda.is_available(): torch.cuda.set_device(local); dev=torch.device('cuda',local)
 else: dev=torch.device('cpu')
 if world>1: dist.init_process_group('nccl' if dev.type=='cuda' else 'gloo',device_id=dev if dev.type=='cuda' else None)
 logging.basicConfig(level=logging.INFO if rank==0 else logging.WARNING,format='%(asctime)s | %(levelname)s | %(message)s',datefmt='%Y-%m-%d %H:%M:%S',force=True)
 return rank,world,dev

def seed_for(seed,split,i):
 d=hashlib.blake2b(f'{seed}:{split}:{i}'.encode(),digest_size=8).digest(); return int.from_bytes(d,'little')
def clean(x):
 if x is None:return ''
 s=x.replace(' ','').strip()
 bad=set(s)-set(STATE_TO_ID)
 if bad: raise ValueError(f'Invalid states: {bad}')
 return s
def nw(L): return 0 if L<25 else min(3,L//25)
def starts(L,i,seed):
 n=nw(L)
 if not n:return []
 r=random.Random(seed_for(seed,'validation',i)); slack=L-n*25
 if n==1:return [r.randint(0,slack)]
 cuts=sorted(r.randint(0,slack) for _ in range(n)); pts=[0]+cuts+[slack]; gaps=[pts[j+1]-pts[j] for j in range(len(pts)-1)]
 out=[]; cur=gaps[0]
 for j in range(n):
  out.append(cur); cur+=25
  if j+1<len(gaps):cur+=gaps[j+1]
 return out
def encode(w): return torch.tensor([CLS_ID]+[STATE_TO_ID[x] for x in w]+[SEP_ID],dtype=torch.long)

def build_units(path,batch_rows,limit):
 pf=pq.ParquetFile(path); units=[]; glob=0; rem=limit
 for rg in range(pf.num_row_groups):
  total=int(pf.metadata.row_group(rg).num_rows)
  if rem is not None and rem<=0:break
  use=total if rem is None else min(total,rem); seen=0
  for b in pf.iter_batches(batch_size=batch_rows,row_groups=[rg],columns=[COL],use_threads=True):
   if seen>=use:break
   vals=b.column(0).to_pylist(); take=min(len(vals),use-seen); vals=vals[:take]
   units.append({'rg':rg,'start':seen,'global':glob+seen,'rows':take,'windows':sum(nw(len(clean(v))) for v in vals)})
   seen+=take
  glob+=total
  if rem is not None:rem-=use
 return units

def assign(units,world):
 a=[[] for _ in range(world)]; load=[0]*world
 for u in sorted(units,key=lambda z:z['windows'],reverse=True):
  r=min(range(world),key=lambda x:load[x]); a[r].append(u); load[r]+=u['windows']
 return a,load

class DS(IterableDataset):
 def __init__(self,path,units,seed,batch_rows):self.path=path;self.units=units;self.seed=seed;self.batch_rows=batch_rows
 def __iter__(self):
  pf=pq.ParquetFile(self.path); by={}
  for u in self.units:by.setdefault(u['rg'],[]).append(u)
  for rg,segs in by.items():
   segs=sorted(segs,key=lambda z:z['start']); si=0; row=0
   for b in pf.iter_batches(batch_size=self.batch_rows,row_groups=[rg],columns=[COL],use_threads=True):
    vals=b.column(0).to_pylist(); bs=row; be=row+len(vals)
    while si<len(segs):
     s=segs[si]; ss=s['start']; se=ss+s['rows']
     if se<=bs:si+=1;continue
     if ss>=be:break
     for rr in range(max(ss,bs),min(se,be)):
      x=clean(vals[rr-bs]); idx=s['global']+(rr-ss)
      for st in starts(len(x),idx,self.seed):yield encode(x[st:st+25])
     if se<=be:si+=1
     else:break
    row=be
    if si>=len(segs):break

class Collate:
 def __init__(self,p,seed):self.p=p;self.g=torch.Generator().manual_seed(seed)
 def __call__(self,ex):
  original=torch.stack(ex); inp=original.clone(); labels=original.clone(); prob=torch.full(labels.shape,self.p);prob[:,0]=0;prob[:,-1]=0
  masked=torch.rand(labels.shape,generator=self.g)<prob; labels[~masked]=-100
  rep=(torch.rand(labels.shape,generator=self.g)<.8)&masked;inp[rep]=MASK_ID
  rnd=(torch.rand(labels.shape,generator=self.g)<.5)&masked&~rep; words=torch.randint(0,VOCAB_SIZE,labels.shape,generator=self.g);inp[rnd]=words[rnd]
  return {'input_ids':inp,'attention_mask':torch.ones_like(inp),'token_type_ids':torch.zeros_like(inp),'labels':labels,'original':original}

def red(x):
 if dist.is_initialized():dist.all_reduce(x)
 return x

@torch.inference_mode()
def embedding_sanity(model,dev):
 pats=['C'*25,'H'*25,'E'*25,'CHE'*8+'C']
 ids=torch.stack([encode(x) for x in pats]).to(dev)
 with torch.autocast(device_type=dev.type,dtype=torch.float16,enabled=dev.type=='cuda'):
  h=model.bert(input_ids=ids,attention_mask=torch.ones_like(ids),token_type_ids=torch.zeros_like(ids)).last_hidden_state[:,1:-1].float().mean(1)
 h=torch.nn.functional.normalize(h,p=2,dim=1); sim=h@h.T
 dif=max((h[i]-h[j]).abs().max().item() for i in range(len(pats)) for j in range(i+1,len(pats)))
 return {'patterns':pats,'cosine_similarity_matrix':sim.cpu().tolist(),'max_pairwise_absolute_difference':dif,'all_embeddings_identical':dif<1e-7}

def main():
 from transformers import BertForMaskedLM, BertTokenizer

 a=args(); rank,world,dev=init_dist(); val=a.dataset_dir/'val.parquet'; out=a.output_json or a.model_dir/'validation_metrics.json'
 tok=BertTokenizer.from_pretrained(a.model_dir); obs=tok('C H E C',add_special_tokens=True)['input_ids']
 if obs!=[2,5,6,7,5,3]:raise RuntimeError(f'Bad tokenizer: {obs}')
 if rank==0: units=build_units(val,a.parquet_batch_rows,a.max_val_proteins)
 else: units=None
 if dist.is_initialized():
  box=[units];dist.broadcast_object_list(box,src=0);units=box[0]
 ass,loads=assign(units,world); expected=sum(loads); proteins=sum(u['rows'] for u in units)
 if rank==0:logging.info('Validation proteins: %d | windows: %d | rank windows: %s',proteins,expected,loads)
 ds=DS(val,ass[rank],a.seed,a.parquet_batch_rows); loader=DataLoader(ds,batch_size=a.batch_size,collate_fn=Collate(a.mlm_probability,a.seed+1000003*rank),drop_last=False,pin_memory=dev.type=='cuda',num_workers=0)
 model=BertForMaskedLM.from_pretrained(a.model_dir).to(dev).eval()
 loss_sum=torch.zeros(1,dtype=torch.float64,device=dev); n=torch.zeros(1,dtype=torch.long,device=dev); correct=torch.zeros_like(n); seen=torch.zeros_like(n); unk=torch.zeros_like(n); cm=torch.zeros((3,3),dtype=torch.long,device=dev); pred_nonbio=torch.zeros_like(n); truec=torch.zeros(3,dtype=torch.long,device=dev); predc=torch.zeros_like(truec)
 with torch.inference_mode():
  for step,b in enumerate(loader,1):
   orig=b.pop('original');seen+=orig.shape[0];unk+=(orig==UNK_ID).sum().to(dev);b={k:v.to(dev,non_blocking=True) for k,v in b.items()};mask=b['labels']!=-100
   with torch.autocast(device_type=dev.type,dtype=torch.float16,enabled=dev.type=='cuda'):o=model(**b)
   logits=o.logits.float();y=b['labels'][mask];p=logits.argmax(-1)[mask]
   if y.numel():
    loss_sum+=torch.nn.functional.cross_entropy(logits[mask],y,reduction='sum').double();n+=y.numel();correct+=(p==y).sum();pred_nonbio+=((p<5)|(p>7)).sum()
    for i,t in enumerate(BIO_IDS):truec[i]+=(y==t).sum();predc[i]+=(p==t).sum()
    for i,t in enumerate(BIO_IDS):
     for j,q in enumerate(BIO_IDS):cm[i,j]+=((y==t)&(p==q)).sum()
   if rank==0 and step%a.logging_steps==0:logging.info('batch %d | local windows %d',step,int(seen.item()))
 for x in (loss_sum,n,correct,seen,unk,cm,pred_nonbio,truec,predc):red(x)
 if n.item() == 0:
  if dist.is_initialized():
   dist.destroy_process_group()
  raise RuntimeError("Validation has no masked tokens; metrics are undefined")
 if rank==0:
  loss=loss_sum.item()/n.item(); per={}
  for i,s in enumerate('CHE'):
   tp=cm[i,i].item();fp=predc[i].item()-tp;fn=truec[i].item()-tp;pr=tp/(tp+fp) if tp+fp else 0;rc=tp/(tp+fn) if tp+fn else 0;f1=2*pr*rc/(pr+rc) if pr+rc else 0;per[s]={'support':truec[i].item(),'precision':pr,'recall':rc,'f1':f1}
  res={'validation_proteins':proteins,'expected_windows':expected,'evaluated_windows':seen.item(),'masked_tokens':n.item(),'mlm_loss':loss,'perplexity':math.exp(loss),'masked_token_accuracy':correct.item()/n.item(),'macro_f1_CHE':sum(v['f1'] for v in per.values())/3,'per_class':per,'confusion_matrix_rows_true_cols_pred_CHE':cm.cpu().tolist(),'predicted_non_CHE_tokens':pred_nonbio.item(),'original_UNK_tokens':unk.item(),'embedding_sanity':embedding_sanity(model,dev)}
  if seen.item()!=expected:raise RuntimeError(f'Coverage mismatch {seen.item()} != {expected}')
  if unk.item()!=0:raise RuntimeError(f'Found {unk.item()} original UNK tokens')
  out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2))
  logging.info('RESULT loss=%.6f perplexity=%.4f accuracy=%.4f%% macroF1=%.6f',loss,res['perplexity'],100*res['masked_token_accuracy'],res['macro_f1_CHE']);logging.info('Per class: %s',per);logging.info('Confusion: %s',res['confusion_matrix_rows_true_cols_pred_CHE']);logging.info('Embedding identical: %s',res['embedding_sanity']['all_embeddings_identical']);logging.info('Saved %s',out)
 if dist.is_initialized():dist.barrier();dist.destroy_process_group()
if __name__=='__main__':main()
