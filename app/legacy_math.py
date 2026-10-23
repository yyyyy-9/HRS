"""Bounded, data-only Equation Native reader for KSEE3 / Equation 3 objects.

No OLE server is activated. Unsupported records fail instead of flattening
mathematics. Container structure follows MS-CFB; MTEF record numbers describe
the stored format, not an executable Office component.
"""
import struct

LIMIT=4*1024*1024


def equation_stream(blob):
    if len(blob)<512 or len(blob)>LIMIT or blob[:8]!=bytes.fromhex('d0cf11e0a1b11ae1'):
        raise ValueError('旧公式 OLE 容器无效')
    u16=lambda b,o:struct.unpack_from('<H',b,o)[0]
    u32=lambda b,o:struct.unpack_from('<I',b,o)[0]
    size=1<<u16(blob,30)
    if size not in (512,4096) or u16(blob,32)!=6:raise ValueError('旧公式 OLE 扇区格式无效')
    def sector(i):
        start=(i+1)*size
        if i>=len(blob)//size or start+size>len(blob):raise ValueError('旧公式 OLE 扇区越界')
        return blob[start:start+size]
    fat_ids=list(struct.unpack_from('<109I',blob,76))
    # Equation objects are small; an indirect DIFAT is outside this importer.
    if u32(blob,72)!=0 or u32(blob,44)>109:raise ValueError('旧公式 OLE 超过支持的容器大小')
    fat=b''.join(sector(i) for i in fat_ids[:u32(blob,44)])
    def chain(start,table,unit,get):
        seen=set();out=[]
        while start<0xfffffffa:
            if start in seen or start*4+4>len(table):raise ValueError('旧公式 OLE 链无效')
            seen.add(start);out.append(get(start))
            if len(out)*unit>LIMIT:raise ValueError('旧公式 OLE 超过大小限制')
            start=u32(table,start*4)
        if start!=0xfffffffe:raise ValueError('旧公式 OLE 链没有正确结束')
        return b''.join(out)
    directory=chain(u32(blob,48),fat,size,sector);root=entry=None
    for offset in range(0,len(directory),128):
        item=directory[offset:offset+128]
        if len(item)!=128:raise ValueError('旧公式 OLE 目录不完整')
        count=u16(item,64)
        if item[66] not in (2,5):continue
        if count<2 or count>64 or count%2:raise ValueError('旧公式 OLE 流名称无效')
        name=item[:count-2].decode('utf-16le')
        if item[66]==5:root=item
        if name=='Equation Native':
            if entry is not None:raise ValueError('旧公式 OLE 数学流重复')
            entry=item
    if root is None or entry is None:raise ValueError('旧公式缺少 Equation Native 数学数据')
    length=struct.unpack_from('<Q',entry,120)[0]
    if length>LIMIT:raise ValueError('旧公式数学流超过限制')
    if length>=u32(blob,56):raw=chain(u32(entry,116),fat,size,sector)
    else:
        mini=chain(u32(root,116),fat,size,sector)
        mini_fat=chain(u32(blob,60),fat,size,sector)
        def small(i):
            if i*64+64>len(mini):raise ValueError('旧公式 OLE 小扇区越界')
            return mini[i*64:i*64+64]
        raw=chain(u32(entry,116),mini_fat,64,small)
    if len(raw)<length:raise ValueError('旧公式数学流不完整')
    return raw[:length]


class MTEF3:
    def __init__(self,data):
        if len(data)<5 or len(data)>LIMIT or data[0]!=3 or data[1]!=1:
            raise ValueError('尚不支持此旧公式版本；请在 WPS 中转换为原生公式后复制')
        self.data=data;self.pos=5;self.records=0

    def take(self,n=1):
        if n<0 or self.pos+n>len(self.data):raise ValueError('旧公式数学记录不完整')
        out=self.data[self.pos:self.pos+n];self.pos+=n;return out

    def byte(self):return self.take()[0]

    def word(self):return struct.unpack('<H',self.take(2))[0]

    def zstring(self):
        end=self.data.find(b'\0',self.pos,self.pos+256)
        if end<0:raise ValueError('旧公式字体记录无效')
        self.pos=end+1

    def objects(self,depth=0):
        if depth>48:raise ValueError('旧公式嵌套超过限制')
        parts=[]
        while True:
            self.records+=1
            if self.records>20000:raise ValueError('旧公式记录超过限制')
            tag=self.byte();kind=tag&15;flags=tag&240
            allowed={0:0,1:240,2:176,3:128,4:160,5:128,6:128}.get(kind,0)
            if flags&~allowed:raise ValueError('旧公式包含尚不支持的记录标志')
            if flags&128:
                x,y=self.take(2)
                if (x,y)==(128,128):self.take(4)
            if kind==0:return parts
            if kind in range(10,15):continue
            if kind==8:
                self.take(2);self.zstring();continue
            if kind==9:
                value=self.byte();self.take(3 if value==100 else 2 if value==101 else 1);continue
            if kind==7:
                self.take(self.byte()*3);continue
            if kind==1:
                if flags&64:self.take(2)
                if flags&32:raise ValueError('尚不支持旧公式中的自定义制表标尺')
                parts.append(''.join(self.objects(depth+1)) if not flags&16 else '')
            elif kind==2:
                face=self.byte();code=self.word();char=chr(code)
                if face not in (129,130,131,132,133,134,135,136):
                    raise ValueError('旧公式包含尚不支持的自定义字体')
                if face in (132,133) and code<128:
                    raise ValueError('旧公式希腊字母没有明确Unicode编码')
                if 0xe000<=code<=0xf8ff or code<32 or 0xd800<=code<=0xdfff:
                    raise ValueError('旧公式包含尚不支持的专用数学字符：'+hex(code))
                char={'{':r'\{','}':r'\}','\\':r'\backslash ','%':r'\%','#':r'\#','&':r'\&','_':r'\_','^':r'\hat{}','~':r'\sim '}.get(char,char)
                if face in (129,130):char=r'\mathrm{'+char+'}'
                elif face==135:char=r'\boldsymbol{'+char+'}'
                if flags&32:
                    embell=self.objects(depth+1)
                    for accent in embell:char=accent.replace('@',char)
                parts.append(char)
            elif kind==6:
                which=self.byte()
                accents={2:r'\dot{@}',3:r'\ddot{@}',4:r'\dddot{@}',5:r"{@}'",6:r"{@}''",7:r'{}^{\backprime}{@}',8:r'\tilde{@}',9:r'\hat{@}',10:r'\not{@}',11:r'\vec{@}',12:r'\overleftarrow{@}',13:r'\overleftrightarrow{@}',17:r'\bar{@}',18:r"{@}'''"}
                if which not in accents:raise ValueError('尚不支持旧公式重音类型：'+str(which))
                parts.append(accents[which])
            elif kind==3:
                selector,variation,options=self.take(3)
                if options and (selector>12 or options>2):raise ValueError('旧公式模板选项不支持')
                slots=self.objects(depth+1)
                parts.append(self.template(selector,variation,slots))
            elif kind==4:
                self.take(2)
                if flags&32:raise ValueError('尚不支持旧公式中的自定义制表标尺')
                slots=self.objects(depth+1)
                parts.append(r'\begin{gathered}'+r'\\'.join(slots)+r'\end{gathered}')
            elif kind==5:
                _,_,_,rows,cols=self.take(5)
                if not 1<=rows<=30 or not 1<=cols<=30:raise ValueError('旧公式矩阵大小无效')
                partitions=self.take((rows+4)//4+(cols+4)//4)
                if any(partitions):raise ValueError('尚不支持带分隔线的旧公式矩阵')
                cells=self.objects(depth+1)
                if len(cells)!=rows*cols:raise ValueError('旧公式矩阵单元数不一致')
                parts.append(r'\begin{matrix}'+r'\\'.join('&'.join(cells[i:i+cols]) for i in range(0,len(cells),cols))+r'\end{matrix}')
            else:raise ValueError('尚不支持旧公式记录：'+str(kind))

    @staticmethod
    def template(kind,variation,slots):
        def n(count):
            if len(slots)!=count:raise ValueError('旧公式模板槽位数不一致')
        if kind<=7:
            n(1)
            if variation not in (0,1,2):raise ValueError('旧公式括号形式不支持')
            left,right=[(r'\langle',r'\rangle'),('(',')'),(r'\{',r'\}'),('[',']'),('|','|'),(r'\Vert',r'\Vert'),(r'\lfloor',r'\rfloor'),(r'\lceil',r'\rceil')][kind]
            return r'\left'+('.' if variation==2 else left)+' '+slots[0]+r'\right'+('.' if variation==1 else right)
        if kind==13:
            if variation not in (0,1):raise ValueError('旧公式根式形式不支持')
            if variation==0:
                if len(slots) not in (1,2):raise ValueError('旧公式根式槽位无效')
                if len(slots)==2 and slots[1]:raise ValueError('旧公式平方根包含非空指数')
                return r'\sqrt{'+slots[0]+'}'
            n(2);return r'\sqrt['+slots[1]+']{'+slots[0]+'}'
        if kind in (14,41):
            if variation not in ((0,1) if kind==14 else (0,1,2)):raise ValueError('旧公式分式形式不支持')
            n(2)
            return (r'\frac{'+slots[0]+'}{'+slots[1]+'}' if kind==14 else '{'+slots[0]+'}/{'+slots[1]+'}')
        if kind==15:
            # MTEF3 scripts follow their base in the containing line.
            n(2)
            if variation==0:return '^{'+slots[1]+'}'
            if variation==1:return '_{'+slots[0]+'}'
            if variation==2:return '_{'+slots[0]+'}^{'+slots[1]+'}'
            raise ValueError('旧公式上下标形式不支持')
        if kind in (16,17):
            n(1);command={16:'underline',17:'overline'}[kind]
            if variation not in (0,1):raise ValueError('旧公式装饰形式不支持')
            value='\\'+command+'{'+slots[0]+'}'
            return '\\'+command+'{'+value+'}' if variation==1 and kind in (16,17) else value
        raise ValueError('尚不支持旧公式模板：'+str(kind))


def ole_to_tex(blob):
    data=equation_stream(blob)
    if len(data)<28:raise ValueError('旧公式数学头不完整')
    offset=struct.unpack_from('<H',data)[0];length=struct.unpack_from('<I',data,8)[0]
    if offset<28 or offset+length>len(data):raise ValueError('旧公式数学范围无效')
    parser=MTEF3(data[offset:offset+length]);value=''.join(parser.objects()).strip()
    if parser.pos!=len(parser.data):raise ValueError('旧公式存在未处理的数学记录')
    if not value:raise ValueError('旧公式为空；整段未插入')
    return value
