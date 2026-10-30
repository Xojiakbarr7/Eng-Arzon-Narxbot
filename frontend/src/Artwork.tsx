import { useEffect, useState } from 'react'
import type { Product } from './types'

// Never pass a decorative illustration off as a real product photograph.
export default function Artwork({product,hero=false}:{product:Pick<Product,'name'|'image_url'>;hero?:boolean}) {
 const [failed,setFailed]=useState(false)
 const image=product.image_url
 useEffect(()=>setFailed(false),[image])
 if(image && /^https:\/\//i.test(image) && !failed) {
  return <img src={image} alt={product.name} loading={hero?'eager':'lazy'}
    referrerPolicy="no-referrer" onError={()=>setFailed(true)}
    className={`artwork product-photo ${hero?'hero-artwork':''}`}
    style={{width:'100%',height:'100%',objectFit:'contain',display:'block'}}/>
 }
 return <div className={`artwork photo-unavailable ${hero?'hero-artwork':''}`}
   role="img" aria-label={`${product.name}: mahsulot rasmi mavjud emas`}
   style={{width:'100%',height:'100%',minHeight:120,display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',padding:16,color:'var(--muted,#718096)',fontSize:13}}>
   Rasm mavjud emas
 </div>
}
