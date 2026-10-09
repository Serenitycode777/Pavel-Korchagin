import re
SHORT = ("а|б|без|бы|в|во|для|до|для|ж|же|за|и|из|или|к|ко|ли|на|над|не|ни|но|о|об|от|по|под|при|про|с|со|у|что|чтоб|чтобы|как|когда|если|то|это|же|да|нет|уже|ещё|только|через|между|перед|из-за|на|я|мы|вы|он|она|они|мне|мои|моё|мой|вас|нас|их|его|её|ей|ему|там|тут|где|ни|ведь|вот|даже|просто|либо|чем|так|всё|все|очень")
PAT = re.compile(r'(?<![\w-])(' + SHORT + r')[ ](?=\S)', re.I)
def fix_text(t):
    prev=None
    while prev!=t:
        prev=t; t=PAT.sub(lambda m:m.group(1)+' ',t)
    t=re.sub(r' ([—–-]) ',' \\1 ',t)
    return t
def fix_html(h):
    """только текст вне тегов, script, style, textarea"""
    out=[];pos=0
    for m in re.finditer(r'<(script|style|textarea)\b.*?</\1>|<[^>]+>',h,re.S|re.I):
        out.append(fix_text(h[pos:m.start()])); out.append(m.group(0)); pos=m.end()
    out.append(fix_text(h[pos:]))
    return ''.join(out)
