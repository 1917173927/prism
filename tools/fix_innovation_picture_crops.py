"""Apply exact source rectangles to native PPT picture objects, preserving raster bytes."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
import json

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/"output"/"innovation-animation-20261007"
NS={"p":"http://schemas.openxmlformats.org/presentationml/2006/main",
    "a":"http://schemas.openxmlformats.org/drawingml/2006/main",
    "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
for prefix,uri in NS.items():
    E.register_namespace(prefix,uri)
manifest=json.loads((BUILD/"parts-manifest.json").read_text(encoding="utf-8"))
changes={}
with ZipFile(BUILD/"candidate.pptx") as source:
    for spec in manifest["slides"]:
        filename=f'ppt/slides/slide{spec["slide"]}.xml'
        root=E.fromstring(source.read(filename))
        pictures=root.findall(".//p:pic",NS)
        assert len(pictures)==len(spec["pieces"])
        for picture,piece in zip(pictures,spec["pieces"]):
            a,b,c,d=piece["sourceRect"]
            blip_fill=picture.find("p:blipFill",NS)
            rect=blip_fill.find("a:srcRect",NS)
            if rect is None:
                rect=E.Element("{"+NS["a"]+"}srcRect")
                blip_fill.insert(1,rect)
            rect.attrib.clear()
            rect.attrib.update(l=str(round(a/1672*100000)),t=str(round(b/941*100000)),
                               r=str(round((1672-c)/1672*100000)),b=str(round((941-d)/941*100000)))
        changes[filename]=E.tostring(root,encoding="utf-8",xml_declaration=True)
    with ZipFile(BUILD/"cropped-candidate.pptx","w") as output:
        for member in source.infolist():
            output.writestr(member,changes.get(member.filename,source.read(member.filename)))
with ZipFile(BUILD/"candidate.pptx") as before,ZipFile(BUILD/"cropped-candidate.pptx") as after:
    assert before.namelist()==after.namelist()
    assert all(before.read(n)==after.read(n) for n in before.namelist() if n not in changes)
    for spec in manifest["slides"]:
        root=E.fromstring(after.read(f'ppt/slides/slide{spec["slide"]}.xml'))
        for picture,piece in zip(root.findall(".//p:pic",NS),spec["pieces"]):
            rect=picture.find("p:blipFill/a:srcRect",NS)
            a,b,c,d=piece["sourceRect"]
            assert dict(rect.attrib)=={"l":str(round(a/1672*100000)),"t":str(round(b/941*100000)),
                                      "r":str(round((1672-c)/1672*100000)),"b":str(round((941-d)/941*100000))}
print("PASS: 42 exact native crop rectangles; all source image bytes preserved")
