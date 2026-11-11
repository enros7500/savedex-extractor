"""Readable reporting of existing evidence; no inference or external calls."""
import re

def text(value):
    # Source text is untrusted: keep terminal escape/control characters out.
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', str(value)).strip()

def render_summary(result):
    source=result['source'];coverage=result['coverage'];items=result['items']
    kinds={e['source_type'] for e in result['evidence']}
    description='author_description' in kinds
    audio=bool(coverage['transcript_ranges'])
    visual=bool(coverage['visual_positions'])
    reviewed=[]
    if description:reviewed.append('author description')
    if audio:reviewed.append('local audio transcription')
    if visual:reviewed.append('sampled images / OCR')
    lines=['Extraction summary',f"Source: {text(source['canonical_url'] or source['input_url'])}",f"Topic: {text(result['topic']['label'])}",f"Status: {result['status']}"]
    if source['publisher_author']:lines.append('Author: @'+text(source['publisher_author']))
    lines.append('Reviewed: '+('Description only' if description and not audio and not visual else ', '.join(reviewed) or 'no usable content'))
    if coverage['unexamined_asset_ids']:
        lines.append(f"Media not reviewed: {len(coverage['unexamined_asset_ids'])} asset(s).")
    lines.extend(['','Extracted information:'])
    if not items:lines.append('No evidence-backed items were extracted.')
    for n,item in enumerate(items,1):
        title=text(item['title']);summary=text(item['summary'])
        lines.append(f'{n}. {title}'+(f' — {summary}' if summary and summary.casefold()!=title.casefold() else ''))
        for uncertainty in item['uncertainties']:
            lines.append('   Uncertainty: '+text(uncertainty.get('reason','Unresolved information.')))
    for collection in result['collections']:
        expected=collection['expected_count']
        count=len(collection['item_ids'])
        if expected is not None:lines.append(f"Collection: {text(collection['label'])}: {count} of {expected} announced items recovered.")
    warnings=list(dict.fromkeys([*coverage['missing_information'],*(g['reason'] for g in result['follow_up']['extraction_gaps']),*(i['message'] for i in result['issues'])]))
    if warnings:lines.extend(['','Unresolved information:',*('- '+text(w) for w in warnings)])
    limitations=list(dict.fromkeys(coverage['limitations']))
    if limitations:lines.extend(['','Limitations:',*('- '+text(w) for w in limitations)])
    lines.append('')
    if result['status']=='error':conclusion='Extraction failed. No complete result is available.'
    elif result['status']=='partial':conclusion=f'{len(items)} item(s) extracted, with unresolved gaps.'
    else:conclusion=f'{len(items)} item(s) extracted. The extractor marked the reviewed sources as sufficient.'
    lines.append('Conclusion: '+conclusion)
    lines.append('This does not confirm full video coverage or verify identities, places, or links.')
    privacy=result['processing']['privacy']
    lines.append('External AI: '+('used' if privacy['external_inference_used'] else 'not used')+'. Web research: '+('used' if privacy['external_web_lookup_used'] else 'not used')+'.')
    elapsed=result.get('extensions',{}).get('runtime:cli_wall_seconds')
    if isinstance(elapsed,(int,float)):lines.append(f'Processing time: {elapsed:.1f} s.')
    return '\n'.join(lines)
