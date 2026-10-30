export async function api<T>(path:string, options:RequestInit={}):Promise<T> {
  const headers=new Headers(options.headers)
  if(options.body && !(options.body instanceof FormData)) headers.set('Content-Type','application/json')
  const initData=window.Telegram?.WebApp.initData
  if(initData) headers.set('X-Telegram-Init-Data',initData)
  const response=await fetch(`/api${path}`,{...options,headers})
  if(!response.ok){ let message=`So‘rov bajarilmadi (${response.status})`; try {const data=await response.json(); message=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail ?? data)}catch{/* use status */} throw new Error(message) }
  if(response.status===204) return undefined as T
  return response.json() as Promise<T>
}
export function money(value:number|null|undefined){ return value==null?'—':new Intl.NumberFormat('uz-UZ').format(Math.round(value)) }
