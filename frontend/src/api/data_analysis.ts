/**
 * 数据分析API
 *
 * 提供卖家数据概览接口调用
 */
import { post } from '@/utils/request'

const DATA_ANALYSIS_PREFIX = '/api/v1/data-analysis'

/** 卖家数据概览请求参数 */
export interface SellerSummaryRequest {
  account_id: number
  date_type: 'recent1d' | 'recent7d' | 'recent30d' | 'customDate'
  date_range?: string
}

/** Banner数据项 */
export interface BannerDataItem {
  name: string
  cycle: string
  data: number
  dataFormat: string
  dataStr: string
  decimal: boolean
  lastData?: number
  lastDataFormat?: string
  lastDataStr?: string
  ratio?: number
  ratioFormat?: string
  extendInfo?: Record<string, string>
}

/** 图表数据项（每日数据） */
export interface GraphDataItem {
  ds: string
  payAmt: number
  payOrdCnt: number
  payByrCnt: number
  showPv: number
  showUv: number
  ipv: number
  ipvUv: number
  vstPv: number
  vstUv: number
  chatUv: number
  aov: number
  rfdAmt: number
  rfdOrdCnt: number
  showItmCnt: number
  ipvItmCnt: number
  stItmCnt: number
  uctr: number
  onlCnt: number
  rptOrdCnt: number
  rptByrCnt: number
  rpr: number
  fstByrPayAmt: number
  rptByrPayAmt: number
  showPvCmpPctl: number
  payOrdCntCmpPctl: number
  rep3minUvRate: number
  [key: string]: number | string
}

/** 卖家数据概览响应数据 */
export interface SellerSummaryData {
  code: string
  data: {
    graphBannerBenchData: {
      bannerDataList: BannerDataItem[]
      graphDataList: GraphDataItem[]
    }
  }
  extendInfo?: {
    realDateRange?: string[]
  }
  msg: string
}

/** API响应格式 */
export interface SellerSummaryResponse {
  success: boolean
  message: string | null
  data: SellerSummaryData | null
}

/**
 * 获取卖家数据概览
 */
export const getSellerSummary = async (
  payload: SellerSummaryRequest,
): Promise<SellerSummaryResponse> => {
  return post<SellerSummaryResponse>(`${DATA_ANALYSIS_PREFIX}/seller-summary`, payload)
}


/** 流量分布请求参数 */
export interface BrowseSummaryRequest {
  account_id: number
  date_type: 'recent1d' | 'recent7d' | 'recent30d' | 'customDate'
  date_range?: string
}

/** 分布数据项 */
export interface ProfileItem {
  profileCode: string
  profileVal: string
  usrRatio: number
  usrRatioFormat: string
}

/** 流量分布响应数据 */
export interface BrowseSummaryData {
  sceneSourceList: ProfileItem[]
  itemCateList: ProfileItem[]
  buyerActiveList: ProfileItem[]
  buyerProvinceList: ProfileItem[]
}

/** 流量分布API响应 */
export interface BrowseSummaryResponse {
  success: boolean
  message: string | null
  data: { code: string; data: BrowseSummaryData; msg: string } | null
}

/**
 * 获取流量分布数据
 */
export const getBrowseSummary = async (
  payload: BrowseSummaryRequest,
): Promise<BrowseSummaryResponse> => {
  return post<BrowseSummaryResponse>(`${DATA_ANALYSIS_PREFIX}/browse-summary`, payload)
}
