import numpy as np
from Bio.Align import substitution_matrices
M = substitution_matrices.load("BLOSUM62")
cols = [str(c) for c in M.alphabet]   # orden de columnas estandar
matrix = {str(a): {str(b): int(M[a,b]) for b in M.alphabet} for a in M.alphabet}

def analyse(char):
    """Replica EXACTAMENTE la logica de BLOSUMSIM para un aminoacido."""
    listaas = dict(map(reversed, matrix[char].items()))   # invierte {aa:score} -> {score:aa}
    listprob = np.array(list(listaas.keys()))
    listprob = listprob[np.where(listprob > 0)]
    opciones = []
    if listprob[1:].size > 0:
        for nn in listprob[1:]:
            chrf = listaas.get(nn)
            prob = np.exp(nn)/sum(np.exp(listprob))
            opciones.append((chrf, int(nn), float(prob)))
    # que aminoacidos con score>0 existian en la fila original, antes de invertir
    reales = sorted([a for a,s in matrix[char].items() if s>0 and a not in 'BZX*'])
    return listprob, opciones, reales

print(f"{'aa':<3} {'opciones (sust, score, prob)':<46} {'etiq p_aug=0.2':<16} perdidos por la inversion")
print("-"*125)
n_self=n_mut=0; lab1=lab0=0
for aa in "ARNDCQEGHILKMFPSTWYV":
    lp, ops, reales = analyse(aa)
    accesibles = {o[0] for o in ops}
    perdidos = [r for r in reales if r not in accesibles and r != aa]
    etiq = []
    for chrf,nn,prob in ops:
        e = 1 if prob >= 0.2 else 0
        etiq.append(f"{chrf}={e}")
        if chrf==aa: n_self+=1
        else: n_mut+=1
        if e==1: lab1+=1
        else: lab0+=1
    s=", ".join(f"{c}({n},{p:.3f})" for c,n,p in ops) or "NINGUNA (no muta)"
    print(f"{aa:<3} {s:<46} {' '.join(etiq):<16} {','.join(perdidos) or '-'}")
print("-"*125)
print(f"opciones que NO mutan (self-match): {n_self} | que si mutan: {n_mut}")
print(f"etiquetadas 1: {lab1} | etiquetadas 0: {lab0}  (p_aug=0.2, el default del script)")
