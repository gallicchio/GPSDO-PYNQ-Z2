"""Tiny s-expression reader for KiCad files."""
def parse(text):
    toks=[]; i=0; n=len(text)
    while i<n:
        c=text[i]
        if c in '()':
            toks.append(c); i+=1
        elif c=='"':
            j=i+1; buf=[]
            while text[j]!='"' or text[j-1]=='\\':
                buf.append(text[j]); j+=1
            toks.append(('str',''.join(buf).replace('\\"','"').replace('\\\\','\\'))); i=j+1
        elif c.isspace():
            i+=1
        else:
            j=i
            while j<n and not text[j].isspace() and text[j] not in '()"': j+=1
            toks.append(('atom',text[i:j])); i=j
    pos=[0]
    def rd():
        t=toks[pos[0]]; pos[0]+=1
        if t=='(':
            out=[]
            while toks[pos[0]]!=')': out.append(rd())
            pos[0]+=1
            return out
        if t==')': raise ValueError("unbalanced")
        return t
    out=[]
    while pos[0]<len(toks): out.append(rd())
    return out

def head(node):
    return node[0][1] if isinstance(node,list) and node and isinstance(node[0],tuple) else None
def kids(node,name):
    return [c for c in node if isinstance(c,list) and head(c)==name]
def kid(node,name):
    k=kids(node,name); return k[0] if k else None
def val(node,i=1):
    v=node[i]
    return v[1] if isinstance(v,tuple) else v
def num(node,i):
    return float(val(node,i))
