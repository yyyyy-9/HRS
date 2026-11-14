"""Bounded, data-only Equation Native reader for Equation Editor and MathType.

No OLE server is activated. Unsupported records fail instead of flattening
mathematics. Container structure follows MS-CFB; MTEF record numbers describe
the stored format, not an executable Office component.
"""
from dataclasses import dataclass
import posixpath
import struct

LIMIT=4*1024*1024
OFFICE='urn:schemas-microsoft-com:office:office'
RELATIONSHIPS='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
EQUATION_CLASSES=frozenset({'equation.3','equation.ksee3','equation.dsmt4'})
ACCENTS={2:r'\dot{@}',3:r'\ddot{@}',4:r'\dddot{@}',5:"{@}'",6:"{@}''",
         7:r'{}^{\backprime}{@}',8:r'\tilde{@}',9:r'\hat{@}',10:r'\not{@}',
         11:r'\vec{@}',12:r'\overleftarrow{@}',13:r'\overleftrightarrow{@}',
         17:r'\bar{@}',18:"{@}'''",29:r'\underline{@}'}
TEX_CHARS={'{':r'\{','}':r'\}','\\':r'\backslash ','%':r'\%','#':r'\#','&':r'\&',
           '_':r'\_','^':r'\hat{}','~':r'\sim ','$':r'\$'}


def embedded_equation(node):
    """Find the single equation object within an OOXML w:object."""
    objects=list(node.iter('{'+OFFICE+'}OLEObject'))
    if len(objects)==1 and objects[0].get('ProgID','').casefold() in EQUATION_CLASSES:
        return objects[0]
    return None


def equation_part(ole, relationships):
    """Resolve only the document's own OLE payload, never its preview or link."""
    relation=relationships.get(ole.get('{'+RELATIONSHIPS+'}id')) or {}
    target=relation.get('Target','')
    if (ole.get('Type','Embed')!='Embed' or relation.get('Type')!=RELATIONSHIPS+'/oleObject'
            or relation.get('TargetMode','Internal')!='Internal' or any(ch in target for ch in '\\:#?')):
        raise ValueError('旧公式缺少有效的内嵌数学关系')
    name=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('word',target))
    if not name.startswith('word/embeddings/'):
        raise ValueError('旧公式资源关系无效')
    return name


def equation_stream(blob):
    if len(blob)<512 or len(blob)>LIMIT or blob[:8]!=bytes.fromhex('d0cf11e0a1b11ae1'):
        raise ValueError('旧公式 OLE 容器无效')
    u16=lambda b,o:struct.unpack_from('<H',b,o)[0]
    u32=lambda b,o:struct.unpack_from('<I',b,o)[0]
    shift=u16(blob,30)
    if shift not in (9,12) or u16(blob,32)!=6:raise ValueError('旧公式 OLE 扇区格式无效')
    size=1<<shift
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


class RecordReader:
    def __init__(self,data,version):
        if not 5<=len(data)<=LIMIT or data[0]!=version or data[1] not in (0,1):
            raise ValueError('旧公式数学版本或平台无效')
        self.data=data;self.pos=5;self.records=0

    def take(self,n=1):
        if n<0 or self.pos+n>len(self.data):raise ValueError('旧公式数学记录不完整')
        out=self.data[self.pos:self.pos+n];self.pos+=n;return out

    def byte(self):return self.take()[0]

    def word(self):return struct.unpack('<H',self.take(2))[0]

    def zstring(self):
        end=self.data.find(b'\0',self.pos,self.pos+256)
        if end<0:raise ValueError('旧公式字符串记录无效')
        value=self.data[self.pos:end]
        self.pos=end+1
        return value

    def record(self,depth):
        if depth>48:raise ValueError('旧公式嵌套超过限制')
        self.records+=1
        if self.records>20000:raise ValueError('旧公式记录超过限制')
        return self.byte()

    def nudge(self):
        if self.take(2)==b'\x80\x80':self.take(4)

    @staticmethod
    def character(code):
        if (0xe000<=code<=0xf8ff or 0xd800<=code<=0xdfff or code<32 or code in (0x7f,0xfffe,0xffff)):
            raise ValueError('旧公式包含尚不支持的专用数学字符：'+hex(code))
        char=chr(code)
        return TEX_CHARS.get(char,char)

    @staticmethod
    def accent(which):
        if which not in ACCENTS:raise ValueError('尚不支持旧公式重音类型：'+str(which))
        return ACCENTS[which]

    def matrix(self,depth,read_cells):
        _,_,_,rows,cols=self.take(5)
        if not 1<=rows<=30 or not 1<=cols<=30:raise ValueError('旧公式矩阵大小无效')
        if any(self.take((rows+4)//4+(cols+4)//4)):
            raise ValueError('尚不支持带分隔线的旧公式矩阵')
        cells=read_cells(depth+1)
        if len(cells)!=rows*cols:raise ValueError('旧公式矩阵单元数不一致')
        return r'\begin{matrix}'+r'\\'.join('&'.join(cells[i:i+cols]) for i in range(0,len(cells),cols))+r'\end{matrix}'


class MTEF3(RecordReader):
    def __init__(self,data):
        super().__init__(data,3)
        if data[1]!=1:raise ValueError('尚不支持此旧公式平台')

    def objects(self,depth=0):
        parts=[]
        while True:
            tag=self.record(depth);kind=tag&15;flags=tag&240
            allowed={0:0,1:240,2:176,3:128,4:160,5:128,6:128}.get(kind,0)
            if flags&~allowed:raise ValueError('旧公式包含尚不支持的记录标志')
            if flags&128:self.nudge()
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
                face=self.byte();code=self.word()
                if face not in (129,130,131,132,133,134,135,136):
                    raise ValueError('旧公式包含尚不支持的自定义字体')
                if face in (132,133) and code<128:
                    raise ValueError('旧公式希腊字母没有明确Unicode编码')
                char=self.character(code)
                if face in (129,130):char=r'\mathrm{'+char+'}'
                elif face==135:char=r'\boldsymbol{'+char+'}'
                if flags&32:
                    embell=self.objects(depth+1)
                    for accent in embell:char=accent.replace('@',char)
                parts.append(char)
            elif kind==6:
                parts.append(self.accent(self.byte()))
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
                parts.append(self.matrix(depth,self.objects))
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


class MTEF5(RecordReader):
    # MTEF 5 record layout is defined by the MathType SDK. Size, font family
    # and color records affect presentation; slots and character styles matter.
    FENCES=(('⟨','⟩'),('(',')'),('{','}'),('[',']'),('|','|'),('‖','‖'),('⌊','⌋'),('⌈','⌉'))
    DELIMITERS={'⟨':r'\langle','⟩':r'\rangle','{':r'\{','}':r'\}',
                '‖':r'\Vert','⌊':r'\lfloor','⌋':r'\rfloor','⌈':r'\lceil','⌉':r'\rceil'}
    FUNCTIONS=frozenset('sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh coth log ln exp lim liminf limsup min max det gcd inf sup arg ker dim deg hom Pr'.split())
    BIG_OPERATORS={'∑':r'\sum','∏':r'\prod','∐':r'\coprod','⋃':r'\bigcup','⋂':r'\bigcap',
                   '∪':r'\bigcup','∩':r'\bigcap','∫':r'\int','∬':r'\iint','∭':r'\iiint','∮':r'\oint'}
    SYMBOLS={0x2212:'-',0xa0:r'\ ',0x21d2:r'\Rightarrow ',0x21d0:r'\Leftarrow ',
             0x21d4:r'\Leftrightarrow ',0x2032:r'{}^{\prime}',0xb1:r'\pm ',0xd7:r'\times ',
             0xf7:r'\div ',0x221e:r'\infty ',0x2260:r'\ne ',0x2264:r'\le ',0x2265:r'\ge ',
             0x2190:r'\leftarrow ',0x2192:r'\rightarrow ',0x2194:r'\leftrightarrow '}
    FENCE_CODES={0xec07:'|',0xec08:'|',0xec09:'‖',0xec0a:'‖',
                 0xf8f0:'⌊',0xf8fb:'⌋',0xf8ee:'⌈',0xf8f9:'⌉'}

    def __init__(self,data):
        super().__init__(data,5)
        if not self.zstring() or (options:=self.byte()) not in (0,1):
            raise ValueError('MathType 公式头无效')
        self.inline=bool(options)
        self.styles={}
        self.explicit_styles=[]

    def uint(self):
        value=self.byte()
        return self.word() if value==255 else value

    def dimensions(self):
        count=self.byte()
        # Each dimension starts with a unit and ends at nibble F. The count
        # refers to dimensions, not bytes, including those in newer profiles.
        in_value=False
        while count:
            value=self.byte()
            for nibble in (value>>4,value&15):
                if not in_value:
                    if nibble>4:raise ValueError('MathType 长度单位无效')
                    in_value=True
                elif nibble==15:
                    count-=1;in_value=False
                    if not count:break
                elif nibble>11:raise ValueError('MathType 长度值无效')

    def metadata(self,kind,depth):
        if kind==8:
            self.uint();self.explicit_styles.append(self.byte())
        elif kind==9:
            value=self.byte()
            if value>7 and value not in (100,101):raise ValueError('MathType 字号无效')
            self.take(3 if value==100 else 2 if value==101 else 1)
        elif 10<=kind<=14:pass
        elif kind==15:self.uint()
        elif kind==16:
            flags=self.byte()
            if flags&~7:raise ValueError('MathType 颜色选项无效')
            self.take(8 if flags&1 else 6)
            if flags&4:self.zstring()
        elif kind==17:
            self.uint();self.zstring()
        elif kind==18:
            if self.byte():raise ValueError('MathType 首选项无效')
            self.dimensions();self.dimensions()
            for face in range(1,self.byte()+1):
                if self.uint():self.styles[face]=self.byte()
        elif kind==19:self.zstring()
        elif kind>=100 and not depth:self.take(self.uint())
        else:raise ValueError('尚不支持 MathType 记录：'+str(kind))

    def options(self,valid):
        flags=self.byte()
        if flags&~(valid|8):raise ValueError('MathType 记录选项无效')
        if flags&8:self.nudge()
        return flags

    def ruler(self,depth):
        if self.record(depth)!=7:raise ValueError('MathType 制表标尺无效')
        self.take(self.byte()*3)

    def glyph(self,flags,depth):
        face=self.byte()-128
        if face==127:face=self.word()-32768
        if flags&0x20 or (flags&0x14)==0x14:
            raise ValueError('MathType 字符缺少可验证的 MTCode')
        code=self.word()
        if flags&4:self.take(1)
        if flags&16:self.take(2)
        raw=self.FENCE_CODES.get(code,chr(code)) if face==22 else chr(code)
        char=self.SYMBOLS[code] if code in self.SYMBOLS else self.character(ord(raw))
        if face<0 and not 1<=-face<=len(self.explicit_styles):raise ValueError('MathType 字体索引无效')
        default=1 if face==7 else 2 if face in (3,4) else 0
        style=self.explicit_styles[-face-1] if face<0 else self.styles.get(face,default)
        if style&~3:raise ValueError('MathType 字形样式无效')
        if face in (1,12) and raw not in TEX_CHARS:
            if not style and not flags&1:return 'text',' ' if code==0xa0 else raw
            char=r'\text{'+(' ' if code==0xa0 else raw)+'}'
        elif style&2 and raw.isascii() and raw.isalpha() and face not in (3,4):char=r'\mathit{'+char+'}'
        elif not style&2 and raw.isalpha():char=r'\mathrm{'+char+'}'
        if style&1:char=r'\boldsymbol{'+char+'}'
        accent=self.objects(depth+1,'accent') if flags&1 else []
        for mark in accent:char=mark.replace('@',char)
        if not accent and face==2 and raw.isascii() and raw.isalpha() and not style:
            return ('function_start' if flags&2 else 'function',raw)
        return 'char',(raw,char)

    def line_tex(self,parts):
        result=[];name='';text=[]
        def flush():
            nonlocal name
            if name:
                result.append('\\'+name+' ' if name in self.FUNCTIONS else r'\operatorname{'+name+'}')
                name=''
        for kind,value in parts:
            if kind=='text':
                flush();text.append(value);continue
            if text:
                result.append(r'\text{'+''.join(text)+'}');text.clear()
            if kind=='function_start':flush()
            if kind in ('function','function_start'):name+=value
            else:
                flush()
                if kind=='tex' and value.startswith(('_','^')) and not result:
                    result.append('{}')
                result.append(value[1] if kind=='char' else value)
        flush()
        if text:result.append(r'\text{'+''.join(text)+'}')
        return ''.join(result)

    def objects(self,depth=0,context='root'):
        parts=[]
        while (kind:=self.record(depth)):
            if kind==1 and context in ('root','slots','template'):
                flags=self.options(7)
                if flags&4:self.take(2)
                if flags&2:self.ruler(depth+1)
                item=('line','' if flags&1 else self.line_tex(self.objects(depth+1,'line')))
            elif kind==2 and context in ('line','template'):
                item=self.glyph(self.options(0x37),depth)
            elif kind==3 and context=='line':
                self.options(0)
                selector,variation=self.take(2)
                if variation&128:variation=(variation&127)|(self.byte()<<8)
                opts=self.byte()
                if opts>(2 if selector<=9 else 1 if selector==15 else 0):
                    raise ValueError('MathType 模板选项无效')
                item=('tex',self.template(selector,variation,self.objects(depth+1,'template')))
            elif kind==4 and context in ('root','line','slots','template'):
                flags=self.options(2);alignment,_=self.take(2)
                if flags&2:self.ruler(depth+1)
                lines=self.objects(depth+1,'slots')
                if alignment in (4,5):raise ValueError('MathType 多行使用了暂不支持的对齐')
                item=('line' if context in ('slots','template') else 'tex',
                      r'\begin{gathered}'+r'\\'.join(lines)+r'\end{gathered}')
            elif kind==5 and context=='line':
                self.options(0)
                item=('tex',self.matrix(depth,lambda d:self.objects(d,'slots')))
            elif kind==6 and context=='accent':
                self.options(0);item=('tex',self.accent(self.byte()))
            else:
                self.metadata(kind,depth)
                continue
            parts.append(item)
        if context in ('slots','accent'):return [value for _,value in parts]
        return parts

    def template(self,selector,variation,parts):
        slots=[value for kind,value in parts if kind=='line']
        symbols=[value[0] for kind,value in parts if kind=='char']
        def shape(count,signs=0):
            if len(slots)!=count or len(symbols)!=signs or len(parts)!=count+signs:
                raise ValueError('MathType 模板槽位不一致：'+str(selector))
        if 0<=selector<=7 and 1<=variation<=3:
            shape(1,variation.bit_count())
            left,right=self.FENCES[selector]
            # MathType carries the glyph too. Check it so a customized fence
            # cannot silently acquire the selector's default character.
            expected=[s for mask,s in ((1,left),(2,right)) if variation&mask]
            equivalents={'⟨':'〈','⟩':'〉','‖':'∥'}
            if any(actual not in (want,equivalents.get(want)) for actual,want in zip(symbols,expected)):
                raise ValueError('MathType 括号使用了自定义符号')
            a=self.DELIMITERS.get(left,left) if variation&1 else '.'
            b=self.DELIMITERS.get(right,right) if variation&2 else '.'
            return r'\left'+a+' '+slots[0]+r'\right'+b+' '
        if selector==10 and variation in (0,1):
            shape(2)
            if bool(slots[1])!=bool(variation):raise ValueError('MathType 根式次数不一致')
            return r'\sqrt'+('['+slots[1]+']' if variation else '')+'{'+slots[0]+'}'
        if selector==11 and variation in (0,1,2,3,6,7):
            # Native editing and round-trip preserve both fraction operands.
            # Diagonal source fractions use the standard stacked form.
            shape(2);return r'\frac{'+slots[0]+'}{'+slots[1]+'}'
        if selector in (12,13,32,33) and variation==0:
            shape(1,1 if selector in (32,33) else 0)
            if symbols and symbols[0] not in ({32:('~','̃'),33:('^','̂')}[selector]):
                raise ValueError('MathType 模板使用了自定义重音')
            command={12:'underline',13:'overline',32:'widetilde',33:'widehat'}[selector]
            return '\\'+command+'{'+slots[0]+'}'
        if selector in (27,28,29) and variation in (0,1):
            shape(2)
            if (selector==27 and slots[1]) or (selector==28 and slots[0]):
                raise ValueError('MathType 上下标槽位不一致')
            return ('{}' if variation else '')+('_{'+slots[0]+'}' if slots[0] else '')+('^{'+slots[1]+'}' if slots[1] else '')
        if selector in range(15,23):
            operator_slot=selector in (21,22) and len(slots)==4 and not symbols
            shape(4 if operator_slot else 3,len(symbols))
            if operator_slot:symbols=[slots.pop()]
            main,lower,upper=slots
            if selector==15 and len(symbols) in (2,3) and set(symbols)=={'∫'}:
                operator=r'\iint' if len(symbols)==2 else r'\iiint'
            else:operator=self.BIG_OPERATORS.get(symbols[0]) if len(symbols)==1 else None
            # MathType 6/7 Equation Native writes bits 4/5 and stores lower
            # before upper. Check both slots against the observed flags.
            if (variation&~(0x17f if selector==15 else 0x70) or not operator
                    or bool(lower)!=bool(variation&0x10) or bool(upper)!=bool(variation&0x20)):
                raise ValueError('MathType 大型算符或上下限未能对应')
            limits=r'\limits' if variation&0x40 else r'\nolimits'
            return operator+limits+('_{'+lower+'}' if lower else '')+('^{'+upper+'}' if upper else '')+' '+main
        raise ValueError('尚不支持 MathType 模板：'+str(selector)+'/'+hex(variation))


@dataclass(frozen=True)
class LegacyEquation:
    tex: str
    inline: bool | None


def read_ole(blob):
    data=equation_stream(blob)
    if len(data)<28:raise ValueError('旧公式数学头不完整')
    offset=struct.unpack_from('<H',data)[0];length=struct.unpack_from('<I',data,8)[0]
    if offset<28 or not 5<=length<=len(data)-offset:raise ValueError('旧公式数学范围无效')
    stream=data[offset:offset+length]
    inline=None
    if stream[0]==3:
        parser=MTEF3(stream);value=''.join(parser.objects())
    elif stream[0]==5:
        parser=MTEF5(stream);inline=parser.inline;parts=parser.objects()
        if len(parts)!=1:raise ValueError('MathType 公式缺少唯一的主结构')
        value=parts[0][1]
    else:raise ValueError('尚不支持此旧公式数学版本：'+str(stream[0]))
    if parser.pos!=len(stream):raise ValueError('旧公式存在未处理的数学记录')
    value=value.strip()
    if not value:raise ValueError('旧公式为空；整段未插入')
    return LegacyEquation(value,inline)


def ole_to_tex(blob):
    return read_ole(blob).tex
